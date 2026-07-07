"""
Loader for recorded real sequences (record_sequences.py output).

Recorded takes are raw: ~72 frames at whatever fps the camera delivers.
load_take() converts one to the model's input convention:

  1. aspect-correct the normalized MediaPipe coords (x *= width/height)
  2. resample to TARGET_FPS using the saved timestamps
  3. crop a T_MAX window centered on the MOTION (largest change in hand
     openness) — so the user's reaction time doesn't matter; 'none' takes
     and motionless takes use the middle window
"""

import glob
import os

import numpy as np

from features import frame_features, sequence_features
from synth_sequences import T_MAX

TARGET_FPS = 15.0
DEFAULT_ASPECT = 4 / 3       # takes recorded before frame_size was saved
ONSET_LEAD = 4               # frames of pre-motion context kept in the window


def _openness(seq):
    """Mean fingertip->wrist distance per frame (fist ~0.7, open ~1.7)."""
    return np.array([frame_features(fr)[:5].mean() for fr in seq])


def load_take(path):
    """-> (features (T_MAX, 28), label int)"""
    d = np.load(path)
    lm = d["landmarks"][:, :, :2].astype(np.float64)
    label = int(d["label"])

    if "frame_size" in d:
        w, h = d["frame_size"]
        lm[:, :, 0] *= w / h
    else:
        lm[:, :, 0] *= DEFAULT_ASPECT

    # resample to TARGET_FPS on the timestamp axis
    ts = d["timestamps"].astype(np.float64)
    ts = ts - ts[0]
    n_out = max(int(round(ts[-1] * TARGET_FPS)) + 1, 2)
    t_new = np.arange(n_out) / TARGET_FPS
    idx = np.searchsorted(ts, np.clip(t_new, 0, ts[-1]))
    seq = lm[np.clip(idx, 0, len(lm) - 1)]

    # motion-centered crop
    if len(seq) <= T_MAX:
        start = 0
    else:
        opens = _openness(seq)
        k = np.ones(3) / 3
        vel = np.abs(np.gradient(np.convolve(opens, k, mode="same")))
        peak = int(vel.argmax())
        start = int(np.clip(peak - T_MAX // 2 + ONSET_LEAD,
                            0, len(seq) - T_MAX))
    seq = seq[start:start + T_MAX]
    if len(seq) < T_MAX:
        seq = np.concatenate(
            [seq, np.repeat(seq[-1:], T_MAX - len(seq), axis=0)])

    return sequence_features(seq).astype(np.float32), label


def list_takes(root):
    files = sorted(glob.glob(os.path.join(root, "*", "*.npz")))
    if not files:
        raise SystemExit(f"no .npz sequences under {root}")
    return files


def split_takes(root, test_frac=0.25, seed=0):
    """Stratified per-class train/test split of take files."""
    rng = np.random.default_rng(seed)
    train, test = [], []
    for c in sorted(os.listdir(root)):
        fs = sorted(glob.glob(os.path.join(root, c, "*.npz")))
        if not fs:
            continue
        order = rng.permutation(len(fs))
        n_test = max(1, int(round(len(fs) * test_frac)))
        test += [fs[i] for i in order[:n_test]]
        train += [fs[i] for i in order[n_test:]]
    return train, test
