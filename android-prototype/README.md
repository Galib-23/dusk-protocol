# Dusk Pick & Drop — Android app

The two-tier Dusk Protocol demo as an Android APK: Capacitor wrapping the
React pick-&-drop client, with the **temporal early-exit GRU running in
plain JavaScript** (no ML runtime) on MediaPipe hand landmarks, and a
~70-line native proximity-sensor plugin for Tier 1.

```
Tier 1  ProximityPlugin.java -> proximity (0-5 cm, 3 near/far cycles in 2 s)
                             -> ambient light (7-15+ cm, 2 shadow dips in 2.5 s)
Tier 2  getUserMedia -> MediaPipe HandLandmarker (WASM/GPU)
        -> features.js (28 invariant dims) -> gru.js (exit @ 4/8/12/16/24)
        -> commit: camera OFF + grab/drop event -> pick & drop via backend
```

Gestures are route-scoped: the pick page only commits `grab`, the drop
page only `drop` (other detections are logged as `commit_ignored`).

## Modes (the battery A/B arms)

- **Always-On (baseline)** — camera streams continuously
- **Dusk** — camera off; proximity wave wakes it; early exit or 10 s
  timeout puts it back to sleep

Same binary, mode picked at launch. To bake single-mode APKs instead:
`$env:VITE_FORCED_MODE="always"; npm run apk` (then `"dusk"`), changing
`appId` in `capacitor.config.json` if both must install side-by-side.

## Build

```powershell
npm install
npm run assets     # mediapipe wasm + GRU weights + hand_landmarker.task
npm run apk        # = vite build + cap sync + gradlew assembleDebug
```

APK lands at `android/app/build/outputs/apk/debug/app-debug.apk`.
Install: `adb install -r android/app/build/outputs/apk/debug/app-debug.apk`.

Browser dev (no phone): `npm run dev` — press **P** to simulate a
proximity wave pulse.

## Data accumulation

Every `wake / camera_on / commit / commit_ignored / timeout / camera_off`
event is logged with timestamp + battery %, queued in localStorage, and
background-flushed every 20 s to the server's `POST /log`, which stores it
in Neon Postgres (`dusk_logs` table, auto-created). Pull everything for
analysis at `https://pd.brittoo.xyz/logs.csv` — frames-to-decision,
wake→commit latency, camera-on ms per session: the §7 thesis metrics.

## Backend

`src/config.js` points at `https://pd.brittoo.xyz` (override with
`VITE_API_URL`). The server's CORS allowlist must include
`https://localhost` (Capacitor WebView origin) — already added in
`web-prototype/server/index.js`; redeploy the server for the APK to work.

## Notes

- Model weights come from `../handgesture`: retrain → `python
  export_gru_json.py` → `npm run apk` ships the new model.
- The exit threshold τ lives in `src/config.js` (`TAU = 0.9`). The Phase-3
  battery policy will make τ = f(battery%) — one function in
  `useDuskDetector.jsx`.
- Proximity sensors are usually binary near/far and sit next to the front
  camera — wave within a few cm of the top of the phone.
