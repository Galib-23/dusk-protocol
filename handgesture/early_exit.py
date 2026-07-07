"""
Temporal early-exit model: a tiny GRU over per-frame landmark features with
classification heads at EXITS = (4, 8, 12, 16, 24) frames.

Inference commits at the first head whose calibrated max-softmax clears tau
and predicts a gesture (not 'none') — the camera can stop right there.
Per-head temperature calibration makes one tau meaningful across heads.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from features import SEQ_FEAT_DIM
from gesture_net import CLASSES, NONE
from synth_sequences import EXITS


class EarlyExitGRU(nn.Module):
    def __init__(self, in_dim=SEQ_FEAT_DIM, hidden=128,
                 num_classes=len(CLASSES), exits=EXITS):
        super().__init__()
        self.exits = tuple(exits)
        self.gru = nn.GRU(in_dim, hidden, batch_first=True)
        self.heads = nn.ModuleList(
            nn.Linear(hidden, num_classes) for _ in self.exits)

    def forward(self, x):
        """x: (B, T, F) with T >= max(exits). Returns list of per-head logits."""
        h, _ = self.gru(x)
        return [head(h[:, k - 1]) for head, k in zip(self.heads, self.exits)]

    # ---- streaming interface for live inference ----
    def step(self, x_t, state=None):
        """x_t: (F,) one frame of features. Returns new hidden state."""
        _, state = self.gru(x_t.view(1, 1, -1), state)
        return state

    def head_logits(self, state, head_idx):
        return self.heads[head_idx](state[-1, 0])


@torch.no_grad()
def calibrate_temperatures(logits_per_head, labels_per_head, ignore=-100):
    """Grid-fit one softmax temperature per head on validation logits."""
    temps = []
    grid = np.concatenate([np.arange(0.5, 3.01, 0.05)])
    for logits, labels in zip(logits_per_head, labels_per_head):
        mask = labels != ignore
        lg, lb = logits[mask], labels[mask]
        best_t, best_nll = 1.0, float("inf")
        for t in grid:
            nll = F.cross_entropy(lg / t, lb).item()
            if nll < best_nll:
                best_nll, best_t = nll, float(t)
        temps.append(best_t)
    return temps


@torch.no_grad()
def simulate_policy(logits_per_head, temps, tau, exits=EXITS):
    """
    Anytime exit policy over precomputed per-head logits.

    Returns (pred, frames): per sequence, the emitted class and the frame
    count at commit. Sequences where no head fires end as 'none' at exits[-1].
    """
    n = logits_per_head[0].shape[0]
    pred = np.full(n, NONE, dtype=np.int64)
    frames = np.full(n, exits[-1], dtype=np.int64)
    done = np.zeros(n, dtype=bool)
    for logits, t, k in zip(logits_per_head, temps, exits):
        probs = torch.softmax(logits / t, dim=1).numpy()
        cls = probs.argmax(1)
        conf = probs.max(1)
        fire = (~done) & (cls != NONE) & (conf >= tau)
        pred[fire] = cls[fire]
        frames[fire] = k
        done |= fire
    return pred, frames
