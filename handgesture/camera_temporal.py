"""
Live temporal early-exit demo (thesis Tier 2).

A recognition window opens when a hand appears. Frame features stream into
the GRU; at each exit head (frames 4/8/12/16/24) the calibrated confidence
is checked against tau — first head to clear it commits the gesture and the
camera would shut off right there (simulated by a dark overlay). If no head
fires by frame 24, the window resets silently ('none').

Keys:
  [ / ]  : lower / raise tau (the battery policy will drive this in Phase 3)
  ESC    : quit
"""

import time

import cv2
import numpy as np
import torch
import mediapipe as mp

from features import frame_features
from gesture_net import CLASSES, NONE
from early_exit import EarlyExitGRU

MODEL_PATH = "gesture_temporal.pth"
TAU = 0.90
CAMERA_OFF_SECS = 1.2
FEED_EVERY = 2      # feed the GRU every 2nd camera frame (~30 fps -> ~15 fps,
                    # the rate the model is trained at)

ckpt = torch.load(MODEL_PATH, map_location="cpu")
model = EarlyExitGRU(exits=ckpt["exits"])
model.load_state_dict(ckpt["state_dict"])
model.eval()
EXITS = tuple(ckpt["exits"])
TEMPS = ckpt["temps"]
print(f"Loaded {MODEL_PATH} | exits {EXITS} | temps "
      f"{[round(t, 2) for t in TEMPS]}")

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                       min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise SystemExit("Cannot open camera")

state = None          # GRU hidden state
prev_feat = None
frame_idx = 0
cam_frame = 0
commit = None         # (label, frames_used, conf, time)
COLORS = {"grab": (0, 140, 255), "drop": (0, 255, 0), "none": (160, 160, 160)}


def reset():
    global state, prev_feat, frame_idx
    state, prev_feat, frame_idx = None, None, 0


while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    now = time.time()

    if commit and now - commit[3] < CAMERA_OFF_SECS:
        # camera is (conceptually) off after an early exit
        dark = (frame * 0.25).astype(np.uint8)
        label, k, conf, _ = commit
        cv2.putText(dark, f"{label.upper()} @ {k} frames ({conf:.2f})",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.3,
                    COLORS[label], 3)
        cv2.putText(dark, "camera off - early exit", (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        cv2.imshow("Early-Exit Gesture", dark)
        if (cv2.waitKey(1) & 0xFF) == 27:
            break
        continue
    commit = None

    result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cam_frame += 1
    if result.multi_hand_landmarks:
        lm = result.multi_hand_landmarks[0]
        mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)

        if cam_frame % FEED_EVERY == 0:   # ~15 fps into the model
            pts = np.array([[p.x * w, p.y * h] for p in lm.landmark], np.float32)
            feat = frame_features(pts)
            delta = feat - prev_feat if prev_feat is not None else np.zeros_like(feat)
            prev_feat = feat
            x_t = torch.from_numpy(np.concatenate([feat, delta])).float()

            with torch.no_grad():
                state = model.step(x_t, state)
            frame_idx += 1

            if frame_idx in EXITS:
                i = EXITS.index(frame_idx)
                with torch.no_grad():
                    probs = torch.softmax(model.head_logits(state, i) / TEMPS[i], 0)
                cls = int(probs.argmax())
                conf = float(probs[cls])
                cv2.putText(frame, f"head k={frame_idx}: {CLASSES[cls]} {conf:.2f}",
                            (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 255, 255), 2)
                if cls != NONE and conf >= TAU:
                    commit = (CLASSES[cls], frame_idx, conf, now)
                    reset()
                elif frame_idx >= EXITS[-1]:
                    reset()   # window exhausted -> none, start a fresh window
    else:
        reset()

    cv2.putText(frame, f"window frame {frame_idx}/{EXITS[-1]}   tau={TAU:.2f}",
                (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("Early-Exit Gesture", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == 27:
        break
    if key == ord("["):
        TAU = max(0.5, TAU - 0.05)
    elif key == ord("]"):
        TAU = min(0.99, TAU + 0.05)

cap.release()
cv2.destroyAllWindows()
