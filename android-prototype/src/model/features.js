// Port of handgesture/features.py — per-frame landmark features.
// All values are pairwise distances normalized by hand scale (wrist ->
// middle-MCP), so they're invariant to position, rotation, mirroring and
// camera distance. 14 base features + 14 deltas = 28 model inputs.

const TIPS = [4, 8, 12, 16, 20];
const CURL_PAIRS = [[4, 2], [8, 5], [12, 9], [16, 13], [20, 17]];
const GAP_PAIRS = [[4, 8], [8, 12], [12, 16], [16, 20]];

export const FEAT_DIM = 14;

// landmarks: array of 21 {x, y} in any consistent space (pixels preferred)
export function frameFeatures(lm) {
  const d = (a, b) => Math.hypot(lm[a].x - lm[b].x, lm[a].y - lm[b].y);
  const scale = d(9, 0) + 1e-6;
  const f = new Array(FEAT_DIM);
  let i = 0;
  for (const t of TIPS) f[i++] = d(t, 0) / scale;
  for (const [a, b] of CURL_PAIRS) f[i++] = d(a, b) / scale;
  for (const [a, b] of GAP_PAIRS) f[i++] = d(a, b) / scale;
  return f;
}

// Maintains the delta half of the feature vector across a streaming session.
export class FeatureStream {
  constructor() { this.prev = null; }
  reset() { this.prev = null; }
  next(lm) {
    const f = frameFeatures(lm);
    const x = new Array(2 * FEAT_DIM);
    for (let i = 0; i < FEAT_DIM; i++) {
      x[i] = f[i];
      x[FEAT_DIM + i] = this.prev ? f[i] - this.prev[i] : 0;
    }
    this.prev = f;
    return x;
  }
}
