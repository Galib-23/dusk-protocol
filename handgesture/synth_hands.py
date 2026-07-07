"""
Procedural MediaPipe-style hand landmark generator.

Samples 21-point hand skeletons with parameterized finger curl, spread and
thumb pose, labeled grab / drop / none by construction. Rendering these
through gesture_net.render_silhouette produces training images in exactly
the domain the live camera pipeline operates in, closing the gap between
the segmentation-silhouette dataset and landmark-rendered inference.

Run directly to write a preview grid:  python synth_hands.py
"""

import numpy as np

from gesture_net import GRAB, DROP, NONE

# canonical right hand, palm facing camera, fingers up (image coords, y down)
# wrist = origin, palm width ~= 1
_FINGERS = [5, 9, 13, 17]
_MCP_POS = {5: (-0.32, -0.95), 9: (-0.11, -1.00), 13: (0.11, -0.97), 17: (0.32, -0.88)}
_SEG_LEN = {5: [0.42, 0.26, 0.20], 9: [0.46, 0.30, 0.22],
            13: [0.42, 0.28, 0.20], 17: [0.32, 0.22, 0.18]}
_FAN_DEG = {5: -14, 9: -2, 13: 10, 17: 22}   # natural splay directions


def _chain(start, angles_deg, lengths):
    """Forward-kinematics chain; each angle is cumulative from vertical-up."""
    p = np.asarray(start, dtype=float).copy()
    a = 0.0
    out = []
    for ang, ln in zip(angles_deg, lengths):
        a += np.deg2rad(ang)
        p = p + ln * np.array([np.sin(a), -np.cos(a)])
        out.append(p.copy())
    return out


def _make_hand(curls, spread, thumb_deg, thumb_curl, rng):
    """
    curls: (4,) 0 = fully extended, 1 = fully folded into the palm
    spread: 0 = fingers parallel, 1 = wide fan
    thumb_deg: base direction from vertical (negative = splayed outward)
    thumb_curl: 0 = straight, 1 = folded across the palm
    """
    pts = np.zeros((21, 2))

    cmc = np.array([-0.28, -0.30]) * rng.uniform(0.9, 1.1, 2)
    pts[1] = cmc
    thumb_angles = [thumb_deg,
                    thumb_curl * 55 + rng.normal(0, 4),
                    thumb_curl * 45 + rng.normal(0, 4)]
    pts[2], pts[3], pts[4] = _chain(cmc, thumb_angles,
                                    np.array([0.26, 0.22, 0.20]) * rng.uniform(0.9, 1.1))

    for f, c in zip(_FINGERS, curls):
        base = np.array(_MCP_POS[f]) * rng.uniform(0.95, 1.05, 2)
        pts[f] = base
        alpha = _FAN_DEG[f] * (0.25 + 1.4 * spread) + rng.normal(0, 2.5)
        bends = [alpha + c * 18,
                 c * 95 + rng.normal(0, 5),
                 c * 85 + rng.normal(0, 5)]
        lengths = np.array(_SEG_LEN[f]) * rng.uniform(0.9, 1.1)
        pts[f + 1], pts[f + 2], pts[f + 3] = _chain(base, bends, lengths)

    return pts


def sample_pose(label: int, rng: np.random.Generator) -> np.ndarray:
    """Sample a random (21, 2) landmark array for the requested class."""
    if label == GRAB:
        # fist: all fingers folded; thumb folded or lying alongside
        curls = rng.uniform(0.72, 1.0, 4)
        spread = rng.uniform(0.0, 0.35)
        thumb_deg = rng.uniform(-35, 5)
        thumb_curl = rng.uniform(0.35, 1.0)
    elif label == DROP:
        # fully open: fingers extended and clearly spread, thumb out
        curls = rng.uniform(0.0, 0.12, 4)
        spread = rng.uniform(0.55, 1.0)
        thumb_deg = rng.uniform(-75, -40)
        thumb_curl = rng.uniform(0.0, 0.3)
    else:
        kind = rng.integers(4)
        if kind == 0:      # 1-3 fingers extended (point / peace / three)
            n = int(rng.integers(1, 4))
            curls = rng.uniform(0.75, 1.0, 4)
            curls[rng.choice(4, n, replace=False)] = rng.uniform(0.0, 0.12, n)
            spread = rng.uniform(0.25, 0.9)
            thumb_deg = rng.uniform(-30, 5)
            thumb_curl = rng.uniform(0.4, 1.0)
        elif kind == 1:    # half-open hand (mid-gesture) — must NOT read as drop
            curls = rng.uniform(0.30, 0.55, 4)
            spread = rng.uniform(0.2, 0.7)
            thumb_deg = rng.uniform(-60, -10)
            thumb_curl = rng.uniform(0.2, 0.6)
        elif kind == 2:    # fingers up but together — open-ish, not a spread drop
            curls = rng.uniform(0.0, 0.12, 4)
            spread = rng.uniform(0.0, 0.15)
            thumb_deg = rng.uniform(-40, -10)
            thumb_curl = rng.uniform(0.3, 0.8)
        else:              # thumbs-up: fist but thumb fully out — must NOT read as grab
            curls = rng.uniform(0.75, 1.0, 4)
            spread = rng.uniform(0.0, 0.3)
            thumb_deg = rng.uniform(-85, -60)
            thumb_curl = rng.uniform(0.0, 0.1)
        label = NONE

    pts = _make_hand(curls, spread, thumb_deg, thumb_curl, rng)

    # global orientation / handedness / landmark noise (MediaPipe jitter)
    theta = np.deg2rad(rng.uniform(-35, 35))
    rot = np.array([[np.cos(theta), -np.sin(theta)],
                    [np.sin(theta), np.cos(theta)]])
    pts = pts @ rot.T
    if rng.random() < 0.5:
        pts[:, 0] *= -1
    pts += rng.normal(0.0, rng.uniform(0.010, 0.030), pts.shape)

    return pts * 100.0


if __name__ == "__main__":
    from PIL import Image
    from gesture_net import CLASSES, render_silhouette

    rng = np.random.default_rng(0)
    N = 10
    sheet = Image.new("L", (N * 105, 3 * 105), 40)
    for row, label in enumerate([GRAB, DROP, NONE]):
        for col in range(N):
            mask = render_silhouette(sample_pose(label, rng), 100)
            sheet.paste(Image.fromarray(mask), (col * 105 + 2, row * 105 + 2))
    sheet.save("synth_preview.png")
    print("rows: " + " / ".join(CLASSES))
    print("saved synth_preview.png")
