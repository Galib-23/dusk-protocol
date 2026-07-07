"""
Train the 3-class (grab / drop / none) silhouette gesture model.

Usage:  python train3.py

Two training domains are mixed:
  1. The silhouette image dataset (20 folders remapped to 3 classes)
  2. Synthetic MediaPipe-style landmark poses rendered with the SAME
     renderer the live camera uses (synth_hands.py) — this is what makes
     live grab/drop detection work, since a webcam frame is classified via
     a landmark-rendered silhouette, not a segmentation mask.

The best checkpoint is chosen by the WORST macro-F1 across the two
validation domains, so neither domain is sacrificed for the other.
Saves to gesture3_model.pth and prints test reports for both domains.
"""

import os
import copy
import random

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageFilter
from torch.utils.data import ConcatDataset, DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms
from torchvision.datasets import ImageFolder
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from tqdm import tqdm

from gesture_net import (CLASSES, IMG_SIZE, GestureNet, binarize,
                         remap_class, render_silhouette)
from synth_hands import sample_pose

TRAIN_DIR = os.path.join(os.path.dirname(__file__), "train", "train")
TEST_DIR = os.path.join(os.path.dirname(__file__), "test", "test")
CKPT_PATH = os.path.join(os.path.dirname(__file__), "gesture3_model.pth")

SEED = 10
BATCH_SIZE = 128
EPOCHS = 15
LR = 1e-3
WEIGHT_DECAY = 1e-4
VAL_FRACTION = 0.15
NUM_WORKERS = 4
N_SYNTH_TRAIN = 9000
N_SYNTH_VAL = 900
N_SYNTH_TEST = 1500


class RandomMorphology:
    """Randomly erode/dilate the silhouette to vary stroke thickness."""

    def __call__(self, img):
        r = random.random()
        if r < 0.25:
            return img.filter(ImageFilter.MaxFilter(3))  # dilate
        if r < 0.5:
            return img.filter(ImageFilter.MinFilter(3))  # erode
        return img


train_tf = transforms.Compose([
    transforms.Grayscale(),
    RandomMorphology(),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(20, fill=0),
    transforms.RandomAffine(0, translate=(0.12, 0.12), scale=(0.8, 1.2),
                            shear=5, fill=0),
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Lambda(binarize),
    transforms.RandomErasing(p=0.2, scale=(0.02, 0.10), value=0),
])

eval_tf = transforms.Compose([
    transforms.Grayscale(),
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Lambda(binarize),
])


class Remapped(Dataset):
    """ImageFolder samples remapped from 20 folder labels to the 3 classes."""

    def __init__(self, root, indices=None, transform=None):
        base = ImageFolder(root)
        self.samples = base.samples if indices is None else [base.samples[i] for i in indices]
        self.folder_names = base.classes
        self.transform = transform
        self.labels = [remap_class(self.folder_names[fidx]) for _, fidx in self.samples]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        path, _ = self.samples[i]
        img = Image.open(path)
        if self.transform:
            img = self.transform(img)
        return img, self.labels[i]


class SynthSilhouettes(Dataset):
    """Landmark poses rendered through the live-inference renderer.

    fixed=True gives a reproducible eval set rendered with the live
    defaults; fixed=False resamples pose + render style every access.
    """

    def __init__(self, n, seed, transform=None, fixed=False):
        self.n = n
        self.seed = seed
        self.transform = transform
        self.fixed = fixed
        self.labels = [i % len(CLASSES) for i in range(n)]

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        rng = np.random.default_rng((self.seed, i) if self.fixed else None)
        pts = sample_pose(self.labels[i], rng)
        if self.fixed:
            mask = render_silhouette(pts)   # live defaults
        else:
            mask = render_silhouette(
                pts,
                thickness_scale=rng.uniform(0.20, 0.36),
                forearm_width=rng.uniform(0.80, 1.25),
                close=rng.random() < 0.9,
            )
        img = Image.fromarray(mask)
        if self.transform:
            img = self.transform(img)
        return img, self.labels[i]


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    preds, trues = [], []
    for x, y in loader:
        out = model(x.to(device))
        preds.extend(out.argmax(1).cpu().numpy())
        trues.extend(y.numpy())
    return np.array(trues), np.array(preds)


def report(name, trues, preds):
    print(f"\n===== {name} =====")
    print(classification_report(trues, preds, target_names=CLASSES, digits=4))
    print("Confusion matrix (rows = true, cols = predicted):")
    print(f"{'':>8}" + "".join(f"{c:>8}" for c in CLASSES))
    for i, row in enumerate(confusion_matrix(trues, preds)):
        print(f"{CLASSES[i]:>8}" + "".join(f"{v:>8}" for v in row))


def main():
    torch.manual_seed(SEED)
    random.seed(SEED)
    np.random.seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ---- dataset domain: stratified split on the 3-class labels ----
    full = Remapped(TRAIN_DIR)
    idx = np.arange(len(full))
    train_idx, val_idx = train_test_split(
        idx, test_size=VAL_FRACTION, stratify=full.labels, random_state=SEED)

    ds_train = Remapped(TRAIN_DIR, train_idx, train_tf)
    ds_val = Remapped(TRAIN_DIR, val_idx, eval_tf)
    ds_test = Remapped(TEST_DIR, transform=eval_tf)

    # ---- synthetic landmark-render domain ----
    sy_train = SynthSilhouettes(N_SYNTH_TRAIN, seed=1, transform=train_tf)
    sy_val = SynthSilhouettes(N_SYNTH_VAL, seed=2, transform=eval_tf, fixed=True)
    sy_test = SynthSilhouettes(N_SYNTH_TEST, seed=3, transform=eval_tf, fixed=True)

    combined = ConcatDataset([ds_train, sy_train])
    labels = np.array(ds_train.labels + sy_train.labels)
    counts = np.bincount(labels, minlength=len(CLASSES))
    print("Train class counts (dataset + synth):", dict(zip(CLASSES, counts.tolist())))

    sample_w = (1.0 / counts)[labels]
    sampler = WeightedRandomSampler(sample_w.tolist(),
                                    num_samples=len(combined), replacement=True)

    train_loader = DataLoader(combined, BATCH_SIZE, sampler=sampler,
                              num_workers=NUM_WORKERS, persistent_workers=NUM_WORKERS > 0)
    val_loaders = {"dataset": DataLoader(ds_val, BATCH_SIZE, num_workers=NUM_WORKERS,
                                         persistent_workers=NUM_WORKERS > 0),
                   "synth": DataLoader(sy_val, BATCH_SIZE, num_workers=NUM_WORKERS,
                                       persistent_workers=NUM_WORKERS > 0)}

    model = GestureNet().to(device)
    print(f"GestureNet parameters: {sum(p.numel() for p in model.parameters()):,}")

    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    best_score, best_state = 0.0, None
    for epoch in range(EPOCHS):
        model.train()
        losses = []
        for x, y in tqdm(train_loader, desc=f"Epoch {epoch + 1}/{EPOCHS}", leave=False):
            x, y = x.to(device), y.to(device)
            loss = criterion(model(x), y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        scheduler.step()

        f1s = {}
        for name, loader in val_loaders.items():
            trues, preds = evaluate(model, loader, device)
            f1s[name] = f1_score(trues, preds, average="macro")
        score = min(f1s.values())   # worst domain decides
        marker = ""
        if score > best_score:
            best_score = score
            best_state = copy.deepcopy(model.state_dict())
            # save immediately so an interrupted run keeps its best model
            torch.save({"state_dict": best_state, "classes": CLASSES,
                        "img_size": IMG_SIZE, "val_macro_f1": best_score}, CKPT_PATH)
            marker = "  <- best (saved)"
        print(f"Epoch {epoch + 1:2d} | train loss {np.mean(losses):.4f} | "
              f"val F1 dataset {f1s['dataset']:.4f} | synth {f1s['synth']:.4f}{marker}")

    assert best_state is not None
    model.load_state_dict(best_state)
    print(f"\nBest checkpoint (worst-domain val macro-F1 {best_score:.4f}) -> {CKPT_PATH}")

    trues, preds = evaluate(model, DataLoader(ds_test, BATCH_SIZE, num_workers=NUM_WORKERS), device)
    report("TEST — dataset silhouettes", trues, preds)
    trues, preds = evaluate(model, DataLoader(sy_test, BATCH_SIZE, num_workers=NUM_WORKERS), device)
    report("TEST — synthetic landmark renders", trues, preds)


if __name__ == "__main__":
    main()
