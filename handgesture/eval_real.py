"""
Evaluate the temporal early-exit model on REAL recorded sequences.

Usage:
  python eval_real.py                       # all of sequences/
  python eval_real.py --files real_split.json --part test   # held-out split

Reports per-head accuracy (vs the sequence label, meaningful from k=12 on,
since the gesture is performed right after recording starts) and the exit
policy tau sweep: emitted class accuracy, frames-to-decision, false fires.
"""

import argparse
import glob
import json
import os

import numpy as np
import torch

from early_exit import EarlyExitGRU, simulate_policy
from gesture_net import CLASSES, NONE
from real_data import list_takes, load_take
from synth_sequences import EXITS

CKPT_PATH = os.path.join(os.path.dirname(__file__), "gesture_temporal.pth")
SEQ_DIR = os.path.join(os.path.dirname(__file__), "sequences")
TAUS = [0.50, 0.70, 0.80, 0.90, 0.95, 0.99]


def gather_files(args):
    if args.files:
        with open(args.files) as f:
            return json.load(f)[args.part]
    return list_takes(args.dir)


def tau_table(logits, temps, slabels, taus=TAUS):
    is_g = slabels != NONE
    print(f"\nTau sweep ({int(is_g.sum())} gesture / {int((~is_g).sum())} none):")
    print(f"{'tau':>5} {'gest acc':>9} {'mean fr':>8} {'grab fr':>8} "
          f"{'drop fr':>8} {'false fire':>11}")
    for tau in taus:
        pred, frames = simulate_policy(logits, temps, tau)
        acc = float((pred[is_g] == slabels[is_g]).mean()) if is_g.any() else float("nan")
        ff = float((pred[~is_g] != NONE).mean()) if (~is_g).any() else float("nan")
        fg = frames[slabels == 0].mean() if (slabels == 0).any() else float("nan")
        fd = frames[slabels == 1].mean() if (slabels == 1).any() else float("nan")
        print(f"{tau:>5.2f} {acc:>9.4f} {frames[is_g].mean():>8.2f} "
              f"{fg:>8.2f} {fd:>8.2f} {ff:>11.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=SEQ_DIR)
    ap.add_argument("--files", default=None, help="json with train/test file lists")
    ap.add_argument("--part", default="test", choices=["train", "test"])
    args = ap.parse_args()

    files = gather_files(args)
    ckpt = torch.load(CKPT_PATH, map_location="cpu")
    model = EarlyExitGRU(exits=ckpt["exits"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    temps = ckpt["temps"]

    xs, labels = [], []
    for f in files:
        x, lb = load_take(f)
        xs.append(torch.from_numpy(x))
        labels.append(lb)
    x = torch.stack(xs).float()
    slabels = np.array(labels)
    print(f"{len(files)} sequences | " +
          " ".join(f"{c}:{(slabels == i).sum()}" for i, c in enumerate(CLASSES)))

    with torch.no_grad():
        logits = [o.cpu() for o in model(x)]

    print("\nPer-head argmax == sequence label "
          "(early heads legitimately say 'none' pre-onset):")
    for k, lg in zip(EXITS, logits):
        acc = float((lg.argmax(1).numpy() == slabels).mean())
        print(f"  k={k:>2}: {acc:.4f}")

    tau_table(logits, temps, slabels)


if __name__ == "__main__":
    main()
