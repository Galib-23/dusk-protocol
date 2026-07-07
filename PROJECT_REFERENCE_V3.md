# 🌒 Dusk Protocol

> *Wake only when needed. Decide as early as possible.*

**Dusk Protocol** is a proximity-gated, battery-aware, early-exit deep learning framework for energy-efficient hand gesture recognition on commodity smartphones.

**Thesis title (working):** *Dusk Protocol: A Proximity-Gated, Battery-Aware Early-Exit Framework for Energy-Efficient Gesture Recognition on Commodity Smartphones*

**Authors:** Jasmin Mustary (2010031) · Asadullah Al Galib (2010033) — BSc ECE, RUET
**Supervisors:** Hafsa Binte Kibria (Assistant Professor, ECE) · Moloy Kumar Ghosh (Lecturer, ECE)

> This file is the single source of truth for the project — written for both humans and AI
> coding assistants (Claude Code). It supersedes the v1 Dusk Protocol README. Keep it updated.

---

## ✦ Version history — what changed from v1 and why (defense-ready story)

v1 of Dusk Protocol proposed four co-equal pillars: hierarchical wake-up, Schnorr ZKP
authentication, a gesture pipeline, and cross-device transfer. After literature review and
feasibility analysis, v2 keeps the **spirit** (energy-efficient gesture interaction on phones
people already own) but replaces every mechanism that didn't survive scrutiny:

| v1 element | Verdict | v2 replacement |
|---|---|---|
| Face-api.js "proximity" tier (web) | ❌ Self-contradictory — used the camera to decide whether to turn on the camera | Real hardware **proximity sensor** (Android `TYPE_PROXIMITY`), truly near-zero cost |
| BLE RSSI proximity tier | ❌ Detects nearby *devices*, not an approaching *hand*; spoofable | Same as above — proximity sensor wave-trigger |
| Schnorr "ZKP" authentication | ❌ Functionally a signature challenge-response; no research contribution; a crypto-aware committee member would object | **Cut from thesis scope.** Optional demo-layer only (see §9) |
| "≥60% energy saving" target | ❌ Unmeasurable without a power monitor; CPU-time proxy misses the camera (the real power hog) | Honest metrics: frames-to-decision, FLOPs, camera-on time, controlled on-phone battery A/B (§7) |
| Always-full gesture model | Replaced | **Temporal early-exit** model — the actual DL contribution (§2) |
| Four co-equal contributions | ❌ Four stapled projects, no single question | One research question + supporting system |
| Screen-off always-on ambition | ❌ OS restrictions make it infeasible for third-party apps | Sensing only while **screen on + app foregrounded** |

**One research question:** *How early in a hand gesture can an on-device model commit to a
prediction, and how much energy does early commitment save — under a policy that adapts to
the phone's remaining battery?*

Kept from v1: the name, the mission (commodity phones, no new hardware), the measurement-suite
discipline, the web prototype as a demo/data tool, the open-source + open-dataset goals, and
the grab/drop gesture vocabulary as a nod to the original transfer vision.

---

## ✦ Core contributions (narrow, honest, defensible)

| # | Contribution | Novelty basis |
|---|---|---|
| 1 | **Temporal early-exit gesture model** — emits a prediction mid-gesture as soon as confident; camera shuts off immediately | 3 independent literature checks (2020–2025) found dynamic/early-exit inference applied to gesture only once (sEMG — Xie et al. 2023 ⚠️), none for video/landmark gesture. Fertl et al. (Sensors 2024, read in full ✅) explicitly list per-pulse early prediction as open future work |
| 2 | **Battery-conditioned exit policy** — exit confidence threshold τ scales with remaining battery (full → deliberate, low → frugal) | Battery-state-conditioned inference for gesture essentially unpublished through 2025 across all three searches. ⚠️ Verify "Scale-Gest" (arXiv 2026?) week 1 — if real, differentiate: they *select between* models, we adapt *within* one via exits |
| 3 | **Measured two-tier system on commodity phones** — proximity-sensor wave trigger gating the camera pipeline, evaluated end-to-end, released open-source with a self-recorded landmark dataset | Integration + open evaluation claim, not an invention claim |

**Explicit non-claims (state in thesis):** early-exit networks (BranchyNet/MSDNet), early
action prediction in video, wave-to-wake, and energy-aware inference all pre-exist — we cite
them. The claim is the specific combination, on-device, measured.

---

## ✦ System architecture

```
┌────────────────────────────────────────────────────────────┐
│ Phone app (screen on, app foregrounded — Android first)    │
│                                                            │
│  TIER 1 — Proximity wave trigger (always on while app open)│
│  • Hardware proximity sensor, event-driven, ~zero cost     │
│  • Rule-based state machine: 3 near/far cycles within 2 s  │
│  • NO ML. ~50 lines. Not a claimed contribution.           │
│                    │ trigger                               │
│                    ▼                                       │
│  TIER 2 — Camera + early-exit gesture model                │
│  • Front camera 15–30 fps                                  │
│  • Per frame: MediaPipe Hands → 21 landmarks (x,y,z)       │
│  • Landmark sequence → tiny temporal net (TCN or GRU,      │
│    ~50–200K params) with EXIT HEADS at k = 4/8/12/16/24    │
│    frames                                                  │
│  • max softmax ≥ τ at any head → emit label, STOP,         │
│    camera OFF; else best guess at k_max                    │
│                    │                                       │
│  BATTERY POLICY (contribution #2, one thesis chapter)      │
│  • τ = f(battery%): rule-based first                       │
│    (e.g., 0.95 @ >60% · 0.90 @ 30–60% · 0.80 @ <30%),      │
│    then an optimized mapping on a calibrated drain model   │
│  • Battery% via expo-battery                               │
│                    │                                       │
│  [optional demo layer — §9] grab on phone A / drop on      │
│  phone B triggers an image transfer. Showcase only.        │
└────────────────────────────────────────────────────────────┘
```

**Gesture vocabulary (6–8 classes):** swipe left · swipe right · swipe up · swipe down ·
push · **grab** (open→fist) · **drop** (fist→open) · thumbs-up.

---

## ✦ Tech stack — decisions and known constraints

⚠️ **Expo Go is NOT sufficient.** Proximity sensor + camera frame processors require native
code → use **Expo prebuild + expo-dev-client** (custom dev build; still the Expo workflow).
Budget setup time. Target **Android first** (iOS doesn't expose the proximity sensor to apps
meaningfully — declare out of scope).

| Need | Choice | Notes |
|---|---|---|
| Proximity sensor | **Custom Expo native module** (Kotlin, `expo-modules-api`) | `expo-sensors` does NOT expose proximity. `Sensor.TYPE_PROXIMITY` ≈ 100 lines Kotlin. Most phones report binary near/far — design Tier 1 for 1-bit input |
| Camera frames | `react-native-vision-camera` (frame processors) | Standard per-frame access in RN; needs dev client |
| Hand landmarks | Option A: `react-native-mediapipe` (vision-camera plugin) · Option B: `react-native-fast-tflite` + MediaPipe hand-landmark `.tflite` manually | Prototype both in weeks 1–2, commit to one. Verify maintenance status at project start |
| Temporal model inference | `react-native-fast-tflite` (JSI, multi-output support) | Our exported multi-exit TFLite model runs here |
| Battery level | `expo-battery` | Level + change listener |
| Foreground/screen gating | RN `AppState` + keep-awake during sessions | Also satisfies OS camera rules |
| Battery experiments | Android `BatteryManager` / `adb shell dumpsys batterystats` | For §7 A/B protocol |
| Training | Python + PyTorch; MediaPipe (Python) for offline landmark extraction; export PyTorch → ONNX/ai-edge-torch → TFLite; `fvcore`/`ptflops` for FLOPs | Landmark caches as `.npy` — extract once |
| Web prototype (kept from v1) | React + Vite, ml5.js/MediaPipe JS | Demoted to: data-collection tool, quick demos, recruiting user-study participants. Not an evaluation platform |

**De-risk fallback:** if RN + frame-processor + MediaPipe integration stalls >2 weeks, build
Tier 2 as a native Android (Kotlin) activity using MediaPipe Tasks directly, embedded in the
RN app. The thesis is the model + measurements, not RN purity.

---

## ✦ Datasets

| Dataset | Use | Notes |
|---|---|---|
| **IPN Hand** | Primary training | ~13 classes designed for touchless phone interaction, per-frame labels, manageable size. ⚠️ Verify download + license week 1 |
| **Jester** (20BN/Qualcomm) | Secondary/pretraining | 27 classes, 148K clips, tens of GB — subset if needed. ⚠️ Verify hosting |
| **Dusk dataset (deliverable)** | Fine-tune + live eval + open release | 6–8 gestures × 10–17 people × ~20 reps, recorded with our own app on ≥2 phone models. Consent forms required. Release **landmarks, not raw video** (privacy + v1's open-dataset goal) |

**Key decision:** train on landmark sequences, not pixels → tiny models, laptop-trainable,
smaller domain gap between dataset videos and our camera.

---

## ✦ Work plan (two semesters; Phase 0 gates everything)

**Phase 0 — Setup & verification (2–3 wks)**
- [ ] Verify all ⚠️ references (§8) actually exist — especially Scale-Gest, Xie 2023. Adjust claims if needed
- [ ] IPN Hand downloaded; Jester access confirmed
- [ ] Expo dev-client skeleton runs on a physical Android phone
- [ ] Spike 1: proximity module streams near/far events
- [ ] Spike 2: vision-camera + MediaPipe draws 21 landmarks live
- **Gate:** both spikes pass → proceed; Spike 2 fails → native-activity fallback

**Phase 1 — Baseline (4–6 wks):** landmark caches → single-exit GRU/TCN (target ≥85–90% val)
→ TFLite on phone, latency measured. *This alone is a safe minimal thesis core.*

**Phase 2 — Temporal early-exit (6–8 wks) — THE CORE:** exit heads at 4/8/12/16/24 frames;
joint weighted-CE anytime loss; per-head temperature calibration; τ sweep → accuracy-vs-frames
Pareto curves; per-class exit behavior ("which gestures are easy?"); wire into app with
camera-stop-on-exit.

**Phase 3 — Battery-aware policy (3–4 wks):** rule-based τ = f(battery%); simulated
gesture-stream drain model calibrated with ≥2 real on-phone drain readings; compare
always-full vs fixed-τ vs battery-aware on "gestures served per charge" + accuracy trajectory.

**Phase 4 — System evaluation & user study (4–5 wks):** Tier-1 trigger/false-trigger rates
(pocket, walking, face-near-phone); end-to-end wave→result latency; battery A/B (§7); user
study n=10–15 with SUS; Dusk dataset finalized.

**Phase 5 — Writing & release (4–6 wks):** thesis (blunt Limitations section on energy-proxy
methodology), repo cleanup, dataset release.

**Two-person split:** Student A owns model/training/simulation (Phases 1–3 Python side);
Student B owns app/native modules/camera pipeline/measurements/user study. Shared: data
collection, writing.

---

## ✦ Evaluation plan — what "energy-efficient" means here (be precise)

Report ALL of:
1. **Frames-to-decision** (primary): mean + distribution, per class, per τ
2. **FLOPs/MACs per decision**
3. **On-phone latency** (per frame, per decision)
4. **Camera-on time per interaction** — say explicitly: the camera, not the model, dominates power; early exit saves energy chiefly by cutting camera time
5. **Relative battery drain:** %/30 min, Dusk vs camera-always-on baseline, same phone, fixed brightness + airplane mode, ≥3 repeats, mean±sd
6. **Accuracy at each operating point** → Pareto curves
7. **NEVER claim absolute milliwatts.** No instrument → no absolute power claims. v1's CPU-time logger stays only as a supplementary compute-time metric, clearly labeled

---

## ✦ Key references (⚠️ = open and skim the actual DOI/arXiv page before it enters the bibliography)

**Anchors (multi-source-confirmed):**
- ✅ Fertl et al., "End-to-End Ultrasonic Hand Gesture Recognition," *Sensors* 24(9):2740, 2024 — read in full; cite for early-per-pulse prediction as stated open problem + sensor comparison
- ⚠️ Xie et al., dynamic-inference sEMG gesture on GAP8, *Sensors* 2023 — closest prior
- ⚠️ Kang et al., on-device few-shot HAR, MobileHCI 2025 (arXiv 2508.15413)
- ⚠️ Laskaridis et al., early-exit survey, 2021
- ⚠️ Xu et al., wrist-worn gesture customization, CHI 2022

**Early-exit / anytime foundations:** ⚠️ BranchyNet (ICPR 2016) · ⚠️ MSDNet (ICLR 2018) ·
⚠️ FrameExit (CVPR 2021 — nearest video-domain prior; differentiate: not on-device, not
gesture, no battery policy) · ⚠️ Lattanzi et al., EE for HAR, *Eng. Appl. AI* 2023

**Energy-aware inference context:** ⚠️ **Scale-Gest (arXiv 2026?) — MUST CHECK WEEK 1** ·
⚠️ Tundo et al., ASE 2023 · ⚠️ Zygarde, IMWUT 2020

**Gesture/system context:** ⚠️ SoundWave, CHI 2012 · MediaPipe Hands (Zhang et al. 2020) ·
⚠️ IPN Hand (ICPR 2020) · ⚠️ Jester (ICCVW 2019)

**Rule:** at least one AI-search-sourced citation list in our planning phase had dubious
provenance. Zero unverified references in the final bibliography.

---

## ✦ Risks & mitigations

| Risk | L | Mitigation |
|---|---|---|
| RN + vision-camera + MediaPipe friction | M-H | 2-week timebox → native Android activity fallback |
| Proximity sensor varies across phones (binary vs distance, latency) | M | Design for 1-bit; test ≥2 phones early; report variability as a finding |
| Scale-Gest scoops battery chapter | L-M | Verify week 1; differentiation drafted (within-model vs between-model adaptation); worst case → comparison chapter |
| Dataset ↔ our-pipeline domain gap | M | Landmarks not pixels; fine-tune on Dusk dataset |
| Early exits hurt accuracy | L | A nuanced negative result ("gestures need ≥N frames; exits help only classes X,Y") is still a legitimate finding — report honestly |
| Battery A/B too noisy | M | Longer sessions, ≥3 repeats, fixed protocol, report variance; frames/FLOPs remain primary |

---

## ✦ §9 Optional demo layer (NOT a thesis contribution — do only if ahead of schedule)

To honor v1's origin story: a showcase where **grab** on phone A and **drop** on phone B
transfers an image between them over the local network (plain REST or WebRTC, standard
authenticated channel — no ZKP claims). Worth ~2 days of work for a memorable defense demo.
If time is short, cut without hesitation. It must never appear in the contributions list.

---

## ✦ Repository structure

```
dusk-protocol/
├── PROJECT_REFERENCE.md          ← this file
├── training/                     # Python (Student A)
│   ├── data/                     # landmark caches (.npy), dataset scripts
│   ├── models/                   # tcn.py, gru.py, exits.py
│   ├── train.py · eval.py · export_tflite.py
│   └── simulate_battery.py
├── app/                          # Expo RN app, dev-client (Student B)
│   ├── modules/proximity/        # custom Expo native module (Kotlin)
│   ├── src/
│   │   ├── tier1/waveDetector.ts # state machine + unit tests
│   │   ├── tier2/camera.tsx      # vision-camera + landmarks
│   │   ├── tier2/inference.ts    # fast-tflite, exit logic
│   │   ├── policy/battery.ts     # τ = f(battery%)
│   │   └── screens/
│   └── assets/models/            # .tflite files
├── web-prototype/                # kept from v1 — data collection + demos only
├── measurements/                 # evolved from v1's suite
│   ├── frames/                   # frames-to-decision logs
│   ├── latency/                  # wakeup_timer.ts (kept from v1)
│   ├── battery/                  # A/B drain protocol + results
│   ├── accuracy/                 # gesture_tester.ts (kept from v1)
│   └── energy/cpu_logger.ts      # kept, demoted to supplementary metric
├── reports/                      # generate_report.ts · export_csv.ts (kept from v1)
├── experiments/                  # protocols, configs, raw results
├── demo-transfer/                # §9 optional grab/drop showcase
└── docs/                         # thesis drafts, figures, consent forms
```

---

## ✦ First 5 tasks for Claude Code (in order)

1. Scaffold the Expo app (dev-client, TypeScript), two screens (Home → Session); confirm `npx expo run:android` works on a physical phone.
2. Build the `proximity` Expo native module (Kotlin): near/far events to JS + a debug screen with live event log.
3. Implement `tier1/waveDetector.ts`: configurable N-waves-in-T-seconds state machine + unit tests on synthetic event streams.
4. Integrate vision-camera + MediaPipe hand landmarks; render 21 points live; log landmark sequences to JSONL (this doubles as the Dusk-dataset collection tool).
5. Python: batch-extract MediaPipe landmarks from IPN Hand → `.npy`, plus a GRU baseline trainer with a clean config.

---

*© 2025–2026 Dusk Protocol — RUET ECE. Academic research project.*