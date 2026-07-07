"""
Synthetic landmark SEQUENCES for the temporal early-exit model.

A sequence is T_MAX frames (~1.6 s at 15 fps) of an animated hand:

  grab : open -> fist, random onset t0 and duration d
  drop : fist -> open, random onset and duration
  none : hard negatives — held poses (incl. held fist / held open!),
         partial grab that re-opens, finger counting, thumb-only motion

Because the generator knows the gesture progress p(t), every exit head
gets an ANYTIME label:
  p(t_k) >= DONE_AT      -> gesture label
  p(t_k) <= NOT_STARTED  -> none          (gesture hasn't begun yet)
  in between             -> IGNORE (masked out of the loss)

Run directly for a rendered filmstrip sanity check:  python synth_sequences.py
"""

import numpy as np

from gesture_net import GRAB, DROP, NONE
from synth_hands import pose_hand, sample_pose_params, sample_skeleton

T_MAX = 24
EXITS = (4, 8, 12, 16, 24)
IGNORE = -100
DONE_AT = 0.7
NOT_STARTED = 0.1


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _lerp(a, b, p):
    return a + (b - a) * p


class _Traj:
    """Interpolates hand params between a start and end pose with per-finger lag."""

    def __init__(self, start, end, t0, dur, rng):
        self.start, self.end = start, end
        self.t0, self.dur = t0, dur
        self.lag = rng.uniform(-1.5, 1.5, 4)     # fingers don't move in unison

    def progress(self, t):
        return float(_smoothstep((t - self.t0) / self.dur))

    def params(self, t):
        c0, s0, td0, tc0 = self.start
        c1, s1, td1, tc1 = self.end
        pf = _smoothstep((t - self.t0 - self.lag) / self.dur)   # (4,)
        p = self.progress(t)
        return (_lerp(np.asarray(c0, float), np.asarray(c1, float), pf),
                _lerp(s0, s1, p), _lerp(td0, td1, p), _lerp(tc0, tc1, p))


def _open_params(rng):
    return (rng.uniform(0.0, 0.18, 4), rng.uniform(0.35, 1.0),
            rng.uniform(-75, -40), rng.uniform(0.0, 0.25))


def _fist_params(rng):
    return (rng.uniform(0.75, 1.0, 4), rng.uniform(0.0, 0.3),
            rng.uniform(-30, 5), rng.uniform(0.4, 1.0))


def _make_traj(label, rng):
    """Returns (traj, gesture_progress_matters). For NONE sequences the
    'progress' never labels a gesture."""
    t0 = rng.uniform(0, 10)
    dur = rng.uniform(4, 14)
    if label == GRAB:
        return _Traj(_open_params(rng), _fist_params(rng), t0, dur, rng), True
    if label == DROP:
        return _Traj(_fist_params(rng), _open_params(rng), t0, dur, rng), True

    kind = rng.integers(4)
    if kind == 0:      # held pose for the whole window (open, fist, count, ...)
        p = sample_pose_params(rng.integers(3), rng)   # any static class pose
        return _Traj(p, p, 0, 1, rng), False
    if kind == 1:      # partial grab (or partial drop) that returns — a feint
        base = _open_params(rng) if rng.random() < 0.5 else _fist_params(rng)
        c0 = np.asarray(base[0], float)
        mid = (np.clip(c0 + rng.uniform(0.25, 0.45) * (1 if c0.mean() < 0.5 else -1),
                       0, 1),
               base[1], base[2], base[3])
        half = rng.uniform(3, 7)
        out = _Traj(base, mid, t0, half, rng)
        back = _Traj(mid, base, t0 + half + rng.uniform(0, 3), half, rng)
        out.back = back    # chained in _params_at
        return out, False
    if kind == 2:      # counting: 1-2 fingers change, rest stay put
        curls = rng.uniform(0.75, 1.0, 4)
        n0 = int(rng.integers(0, 3))
        curls[rng.choice(4, n0, replace=False)] = rng.uniform(0.0, 0.12, n0)
        end = curls.copy()
        flip = rng.choice(4, int(rng.integers(1, 3)), replace=False)
        end[flip] = np.where(end[flip] > 0.5,
                             rng.uniform(0.0, 0.12, len(flip)),
                             rng.uniform(0.75, 1.0, len(flip)))
        common = (rng.uniform(0.25, 0.8), rng.uniform(-30, 5), rng.uniform(0.4, 1.0))
        return _Traj((curls, *common), (end, *common), t0, dur, rng), False
    # thumb-only motion on a fist (thumbs-up appearing/disappearing)
    curls = rng.uniform(0.75, 1.0, 4)
    a = (curls, rng.uniform(0.0, 0.3), rng.uniform(-30, 5), rng.uniform(0.5, 1.0))
    b = (curls, a[1], rng.uniform(-85, -60), rng.uniform(0.0, 0.1))
    if rng.random() < 0.5:
        a, b = b, a
    return _Traj(a, b, t0, dur, rng), False


def _params_at(traj, t):
    back = getattr(traj, "back", None)
    if back is not None and t > back.t0:
        return back.params(t)
    return traj.params(t)


def sample_sequence(label: int, rng: np.random.Generator):
    """
    Returns:
      seq         (T_MAX, 21, 2) landmark frames
      head_labels (len(EXITS),) anytime label per exit head (IGNORE = masked)
      label       the sequence-level class
    """
    skel = sample_skeleton(rng)
    traj, is_gesture = _make_traj(label, rng)
    noise = rng.uniform(0.006, 0.020)

    seq = np.empty((T_MAX, 21, 2))
    for t in range(T_MAX):
        pts = pose_hand(skel, *_params_at(traj, t))
        seq[t] = pts + rng.normal(0.0, noise, pts.shape)

    head_labels = np.empty(len(EXITS), dtype=np.int64)
    for i, k in enumerate(EXITS):
        if not is_gesture:
            head_labels[i] = NONE
        else:
            p = traj.progress(k - 1)
            head_labels[i] = (label if p >= DONE_AT
                              else NONE if p <= NOT_STARTED else IGNORE)

    return seq * 100.0, head_labels, label


if __name__ == "__main__":
    from PIL import Image
    from gesture_net import CLASSES, render_silhouette

    rng = np.random.default_rng(1)
    rows = [GRAB, DROP, NONE, NONE]
    sheet = Image.new("L", (T_MAX // 2 * 85, len(rows) * 85), 40)
    for r, label in enumerate(rows):
        seq, heads, _ = sample_sequence(label, rng)
        print(CLASSES[label], "head labels:",
              [CLASSES[h] if h >= 0 else "-" for h in heads])
        for c, t in enumerate(range(0, T_MAX, 2)):
            mask = render_silhouette(seq[t], 80)
            sheet.paste(Image.fromarray(mask), (c * 85 + 2, r * 85 + 2))
    sheet.save("synth_seq_preview.png")
    print("rows: grab / drop / none / none — every 2nd frame")
    print("saved synth_seq_preview.png")
