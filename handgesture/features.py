"""
Per-frame landmark features for the temporal early-exit model.

All features are pairwise distances normalized by hand scale, so they are
invariant to translation, rotation, mirroring and camera distance. That
keeps synthetic training sequences and real MediaPipe landmarks in nearly
the same domain — no silhouette rendering needed.

Layout (14 dims per frame):
  0-4   fingertip -> wrist distance   (openness), thumb/index/middle/ring/pinky
  5-9   fingertip -> own MCP distance (curl)
  10-13 adjacent fingertip gaps       (spread)

sequence_features() appends first differences -> 28 dims per frame.
"""

import numpy as np

FEAT_DIM = 14
SEQ_FEAT_DIM = 2 * FEAT_DIM

_TIPS = [4, 8, 12, 16, 20]
_CURL_PAIRS = [(4, 2), (8, 5), (12, 9), (16, 13), (20, 17)]
_GAP_PAIRS = [(4, 8), (8, 12), (12, 16), (16, 20)]


def frame_features(landmarks) -> np.ndarray:
    """(21, 2+) landmark array -> (14,) float32 feature vector."""
    p = np.asarray(landmarks, dtype=np.float64)[:, :2]
    scale = np.linalg.norm(p[9] - p[0]) + 1e-6   # wrist -> middle MCP

    def d(a, b):
        return np.linalg.norm(p[a] - p[b]) / scale

    f = [d(t, 0) for t in _TIPS]
    f += [d(a, b) for a, b in _CURL_PAIRS]
    f += [d(a, b) for a, b in _GAP_PAIRS]
    return np.asarray(f, dtype=np.float32)


def sequence_features(seq) -> np.ndarray:
    """(T, 21, 2+) landmark sequence -> (T, 28) features (values + deltas)."""
    feats = np.stack([frame_features(fr) for fr in seq])
    deltas = np.diff(feats, axis=0, prepend=feats[:1])
    return np.concatenate([feats, deltas], axis=1)
