# Battery A/B protocol — always-on vs dusk

Goal: show the hierarchical system (proximity wave → camera+model) costs
substantially less energy than an always-on camera pipeline, using honest,
reproducible on-phone measurements (PROJECT_REFERENCE §7 rules: no absolute
watts, report camera-on time as the mechanism, mean ± sd over repeats).

## Fixed conditions (identical for both arms)

- Same phone, same charger history (start each run at the same battery %,
  e.g. 80%, after 10 min rest off-charger)
- Screen brightness fixed (50%), auto-brightness OFF
- Airplane mode ON + Wi-Fi ON (network identical, no SIM radio noise)
- No other foreground apps; notifications off; battery saver OFF
- Phone flat on a desk, same lighting (note lux conditions in the log book)
- App in foreground the whole session (it holds the screen awake)

## Session script (30 min per run)

1. Pick the arm on the mode screen (always / dusk).
2. Every 2 minutes, perform one scripted interaction
   (alternate grab and drop) — 15 interactions per session.
   - dusk arm: wave to wake first, then gesture.
   - between interactions: leave the phone alone (this is where the two
     arms differ — dusk's camera is off, always-on keeps streaming).
3. After 30 min, close the app.
4. Recharge to the starting %, rest 10 min, run the other arm.
5. **≥ 3 repeats per arm**, alternating order (A-B-B-A-A-B) to cancel
   battery-health drift.

The app logs everything automatically (battery every 60 s, camera
intervals, wakes, commits, frames-to-decision) to the server DB.

## Analysis

```
cd measurements
python analyze_logs.py        # pulls https://pd.brittoo.xyz/logs.csv
```

Produces per-session rows + per-mode aggregates and figures:
- `out/battery_drain.png` — battery % vs session time, colored by mode
- `out/camera_duty.png`   — camera duty cycle per mode
- `out/summary.csv`       — table for the thesis

## What to report (thesis §7)

| Metric | Source |
|---|---|
| Camera duty cycle (%) per mode | camera_on/off intervals |
| Battery drain %/30 min, mean ± sd, per mode | battery_sample series |
| Frames-to-decision (mean, median, per class) | commit events |
| Wake→commit latency (ms) | commit events |
| Tier-1 wakes, timeouts (false-wake proxy) | wake/timeout events |
| Gestures served per session | commit counts |

Also record manually per session: date, phone, battery start %, room
lighting, and any anomalies. NEVER convert any of this to watts — no
instrument, no absolute power claims.

## Extra runs worth having

- **Idle-only sessions** (no interactions, 30 min each arm): isolates the
  standby gap — this is where dusk wins hardest.
- **False-trigger session** (dusk, phone in normal desk use / walking with
  phone in hand, no intended waves): count spurious `wake` events.
- Repeat the whole grid on a 2nd phone model if available (sensor
  variability is a legitimate finding).
