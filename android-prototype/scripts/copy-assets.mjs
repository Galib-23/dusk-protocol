// Copies runtime assets into public/ so the APK works fully offline:
//   - MediaPipe tasks-vision WASM bundle
//   - the exported GRU weights from ../handgesture
import { cpSync, mkdirSync, existsSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

const wasmSrc = join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const wasmDst = join(root, "public", "wasm");
cpSync(wasmSrc, wasmDst, { recursive: true });
console.log("copied mediapipe wasm ->", wasmDst);

mkdirSync(join(root, "public", "model"), { recursive: true });

const gru = join(root, "..", "handgesture", "gesture_temporal.json");
if (existsSync(gru)) {
  copyFileSync(gru, join(root, "public", "model", "gesture_temporal.json"));
  console.log("copied GRU weights");
} else {
  console.warn("WARNING: ../handgesture/gesture_temporal.json missing — "
    + "run export_gru_json.py");
}

const task = join(root, "public", "model", "hand_landmarker.task");
if (!existsSync(task)) {
  const url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    + "hand_landmarker/float16/latest/hand_landmarker.task";
  console.log("downloading hand_landmarker.task ...");
  const res = await fetch(url);
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  const { writeFileSync } = await import("node:fs");
  writeFileSync(task, Buffer.from(await res.arrayBuffer()));
  console.log("downloaded hand_landmarker.task");
}
