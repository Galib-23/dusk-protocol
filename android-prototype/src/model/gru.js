// Pure-JS forward pass of the temporal early-exit GRU (PyTorch convention).
// Weights come from handgesture/export_gru_json.py — no ML runtime needed.
// Per-frame cost is ~60k multiply-adds: microseconds on any phone.

const sigmoid = (v) => 1 / (1 + Math.exp(-v));
const dot = (row, x) => {
  let s = 0;
  for (let i = 0; i < row.length; i++) s += row[i] * x[i];
  return s;
};

export const NONE = 2; // classes = [grab, drop, none]

export async function loadModel(url = "/model/gesture_temporal.json") {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to load GRU weights: ${res.status}`);
  return new EarlyExitGRU(await res.json());
}

export class EarlyExitGRU {
  constructor(w) {
    this.w = w;
    this.classes = w.classes;
    this.exits = w.exits;
    this.maxFrames = w.exits[w.exits.length - 1];
    this.reset();
  }

  reset() {
    this.h = new Float32Array(this.w.hidden);
    this.t = 0;
  }

  // x: number[28]. Returns null between exits, or
  // {frame, cls, label, conf, probs} at an exit head.
  step(x) {
    const { hidden: H, w_ih, w_hh, b_ih, b_hh } = this.w;
    const h = this.h;
    const h2 = new Float32Array(H);
    for (let j = 0; j < H; j++) {
      const r = sigmoid(b_ih[j] + dot(w_ih[j], x) + b_hh[j] + dot(w_hh[j], h));
      const z = sigmoid(b_ih[H + j] + dot(w_ih[H + j], x) +
                        b_hh[H + j] + dot(w_hh[H + j], h));
      const n = Math.tanh(b_ih[2 * H + j] + dot(w_ih[2 * H + j], x) +
                          r * (b_hh[2 * H + j] + dot(w_hh[2 * H + j], h)));
      h2[j] = (1 - z) * n + z * h[j];
    }
    this.h = h2;
    this.t += 1;

    const head = this.exits.indexOf(this.t);
    if (head < 0) return null;

    const { w: hw, b: hb } = this.w.heads[head];
    const T = this.w.temps[head];
    const logits = hb.map((b, c) => (b + dot(hw[c], h2)) / T);
    const m = Math.max(...logits);
    const exps = logits.map((l) => Math.exp(l - m));
    const sum = exps.reduce((a, b) => a + b, 0);
    const probs = exps.map((e) => e / sum);
    let cls = 0;
    for (let c = 1; c < probs.length; c++) if (probs[c] > probs[cls]) cls = c;
    return { frame: this.t, cls, label: this.classes[cls], conf: probs[cls], probs };
  }
}
