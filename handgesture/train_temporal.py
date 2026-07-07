"""
Train the temporal early-exit gesture model (thesis contribution #1).

Usage:  python train_temporal.py [--real sequences_dir]

- Trains EarlyExitGRU on synthetic landmark sequences with anytime labels
  (per-head: gesture once >=70% complete, none before onset, masked between)
- Optionally mixes in real recorded sequences (record_sequences.py output)
- Calibrates a softmax temperature per exit head on validation data
- Sweeps tau and reports the accuracy-vs-frames-to-decision Pareto table,
  including per-class frames-to-decision and false-fire rate on 'none'
- Saves checkpoint + calibration to gesture_temporal.pth and the tau sweep
  to results_temporal.csv
"""

import argparse
import copy
import csv
import glob
import json
import os

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import ConcatDataset, DataLoader, Dataset
from sklearn.metrics import f1_score
from tqdm import tqdm

from features import sequence_features
from gesture_net import CLASSES, NONE
from early_exit import EarlyExitGRU, calibrate_temperatures, simulate_policy
from real_data import load_take, split_takes
from synth_sequences import EXITS, IGNORE, T_MAX, sample_sequence

CKPT_PATH = os.path.join(os.path.dirname(__file__), "gesture_temporal.pth")
CSV_PATH = os.path.join(os.path.dirname(__file__), "results_temporal.csv")

SEED = 10
BATCH_SIZE = 256
EPOCHS = 20
LR = 2e-3
WEIGHT_DECAY = 1e-4
N_TRAIN = 12000
N_VAL = 3000
N_TEST = 3000
HEAD_WEIGHTS = [0.5, 0.7, 0.9, 1.0, 1.0]
TAUS = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.97, 0.99]


class SynthSequences(Dataset):
    """fixed=True -> reproducible eval set; fixed=False -> fresh every access."""

    def __init__(self, n, seed, fixed=False):
        self.n, self.seed, self.fixed = n, seed, fixed

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        rng = np.random.default_rng((self.seed, i) if self.fixed else None)
        label = i % len(CLASSES)
        seq, head_labels, _ = sample_sequence(label, rng)
        x = sequence_features(seq)
        return (torch.from_numpy(x), torch.from_numpy(head_labels),
                torch.tensor(label))


class RealSequences(Dataset):
    """Recorded takes (record_sequences.py), loaded via real_data.load_take —
    resampled to 15 fps and motion-centered. The loader places the motion
    around the window center, so heads at k >= 16 get the sequence label and
    earlier heads are masked (gesture may still be in progress)."""

    def __init__(self, files):
        self.files = files

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        x, label = load_take(self.files[i])
        head_labels = np.array(
            [label if (k >= 16 or label == NONE) else IGNORE for k in EXITS],
            dtype=np.int64)
        return (torch.from_numpy(x), torch.from_numpy(head_labels),
                torch.tensor(label))


def anytime_loss(logits_per_head, head_labels):
    loss = 0.0
    for w, logits, i in zip(HEAD_WEIGHTS, logits_per_head,
                            range(len(EXITS))):
        loss = loss + w * nn.functional.cross_entropy(
            logits, head_labels[:, i], ignore_index=IGNORE)
    return loss / sum(HEAD_WEIGHTS)


@torch.no_grad()
def collect(model, loader, device):
    """Run the model over a loader; returns per-head logits/labels + seq labels."""
    model.eval()
    logits = [[] for _ in EXITS]
    hlabels = [[] for _ in EXITS]
    slabels = []
    for x, hl, sl in loader:
        outs = model(x.to(device))
        for i, o in enumerate(outs):
            logits[i].append(o.cpu())
            hlabels[i].append(hl[:, i])
        slabels.append(sl)
    return ([torch.cat(l) for l in logits],
            [torch.cat(l) for l in hlabels],
            torch.cat(slabels).numpy())


def head_scores(logits, hlabels):
    accs = []
    for lg, lb in zip(logits, hlabels):
        m = lb != IGNORE
        accs.append((lg[m].argmax(1) == lb[m]).float().mean().item())
    return accs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", default=None,
                    help="directory of recorded .npz sequences to mix in")
    ap.add_argument("--real-repeat", type=int, default=20,
                    help="oversampling factor so real takes aren't drowned "
                         "by the synthetic pool")
    ap.add_argument("--real-test-frac", type=float, default=0.25)
    args = ap.parse_args()

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device} | exits at frames {EXITS}")

    train_ds = SynthSequences(N_TRAIN, seed=1)
    real_test_files = None
    if args.real:
        train_files, real_test_files = split_takes(
            args.real, test_frac=args.real_test_frac, seed=SEED)
        with open(os.path.join(os.path.dirname(__file__), "real_split.json"),
                  "w") as f:
            json.dump({"train": train_files, "test": real_test_files}, f, indent=1)
        print(f"Real takes: {len(train_files)} train (x{args.real_repeat} "
              f"oversampled) + {len(real_test_files)} held-out test "
              f"(real_split.json)")
        train_ds = ConcatDataset(
            [train_ds] + [RealSequences(train_files)] * args.real_repeat)
    val_ds = SynthSequences(N_VAL, seed=2, fixed=True)
    test_ds = SynthSequences(N_TEST, seed=3, fixed=True)

    train_loader = DataLoader(train_ds, BATCH_SIZE, shuffle=True,
                              num_workers=4, persistent_workers=True)
    val_loader = DataLoader(val_ds, BATCH_SIZE, num_workers=4,
                            persistent_workers=True)
    test_loader = DataLoader(test_ds, BATCH_SIZE, num_workers=4)

    model = EarlyExitGRU().to(device)
    print(f"EarlyExitGRU parameters: {sum(p.numel() for p in model.parameters()):,}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR,
                                  weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    best_score, best_state = 0.0, None
    for epoch in range(EPOCHS):
        model.train()
        losses = []
        for x, hl, _ in tqdm(train_loader, desc=f"Epoch {epoch + 1}/{EPOCHS}",
                             leave=False):
            loss = anytime_loss(model(x.to(device)), hl.to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        scheduler.step()

        logits, hlabels, _ = collect(model, val_loader, device)
        accs = head_scores(logits, hlabels)
        score = float(np.mean(accs))
        marker = ""
        if score > best_score:
            best_score = score
            best_state = copy.deepcopy(model.state_dict())
            marker = "  <- best (saved)"
        acc_str = " ".join(f"k{k}:{a:.3f}" for k, a in zip(EXITS, accs))
        print(f"Epoch {epoch + 1:2d} | loss {np.mean(losses):.4f} | "
              f"val head acc {acc_str}{marker}")
        if marker:
            torch.save({"state_dict": best_state, "classes": CLASSES,
                        "exits": EXITS, "temps": [1.0] * len(EXITS)}, CKPT_PATH)

    assert best_state is not None
    model.load_state_dict(best_state)

    # ---- per-head temperature calibration on validation ----
    logits, hlabels, _ = collect(model, val_loader, device)
    temps = calibrate_temperatures(logits, hlabels, ignore=IGNORE)
    print("\nCalibrated temperatures per head:",
          {f"k{k}": round(t, 2) for k, t in zip(EXITS, temps)})
    torch.save({"state_dict": best_state, "classes": CLASSES,
                "exits": EXITS, "temps": temps}, CKPT_PATH)
    print(f"Saved -> {CKPT_PATH}")

    # ---- test: per-head accuracy + tau sweep ----
    logits, hlabels, slabels = collect(model, test_loader, device)
    accs = head_scores(logits, hlabels)
    print("\nTest per-head accuracy (anytime labels):")
    for k, a in zip(EXITS, accs):
        print(f"  k={k:>2} frames: {a:.4f}")

    is_gesture = slabels != NONE
    print(f"\nTau sweep ({is_gesture.sum()} gesture / "
          f"{(~is_gesture).sum()} none sequences):")
    hdr = (f"{'tau':>5} {'gest acc':>9} {'mean fr':>8} {'med fr':>7} "
           f"{'grab fr':>8} {'drop fr':>8} {'false fire':>11}")
    print(hdr)
    rows = []
    for tau in TAUS:
        pred, frames = simulate_policy(logits, temps, tau)
        g = is_gesture
        acc = float((pred[g] == slabels[g]).mean())
        ff = float((pred[~g] != NONE).mean())
        mg = frames[g & (slabels == 0)].mean()
        md = frames[g & (slabels == 1)].mean()
        row = dict(tau=tau, gesture_acc=round(acc, 4),
                   mean_frames=round(float(frames[g].mean()), 2),
                   median_frames=float(np.median(frames[g])),
                   grab_frames=round(float(mg), 2),
                   drop_frames=round(float(md), 2),
                   false_fire=round(ff, 4))
        rows.append(row)
        print(f"{tau:>5.2f} {row['gesture_acc']:>9.4f} {row['mean_frames']:>8.2f} "
              f"{row['median_frames']:>7.1f} {row['grab_frames']:>8.2f} "
              f"{row['drop_frames']:>8.2f} {row['false_fire']:>11.4f}")

    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote tau sweep -> {CSV_PATH}")
    print(f"Baseline (no early exit): every decision costs {EXITS[-1]} frames.")

    if real_test_files:
        loader = DataLoader(RealSequences(real_test_files), BATCH_SIZE)
        logits, _, slabels = collect(model, loader, device)
        is_g = slabels != NONE
        print(f"\n===== HELD-OUT REAL SEQUENCES ({int(is_g.sum())} gesture / "
              f"{int((~is_g).sum())} none) =====")
        for tau in [0.80, 0.90, 0.95]:
            pred, frames = simulate_policy(logits, temps, tau)
            acc = float((pred[is_g] == slabels[is_g]).mean())
            ff = float((pred[~is_g] != NONE).mean()) if (~is_g).any() else 0.0
            print(f"tau {tau:.2f}: gesture acc {acc:.4f} | mean frames "
                  f"{frames[is_g].mean():.2f} | false fire {ff:.4f}")


if __name__ == "__main__":
    main()
