"""
Live 3-class gesture demo: grab / drop / none.

Pipeline per frame:
  webcam -> MediaPipe Hands (21 landmarks)
         -> render a filled hand silhouette from the landmarks
            (matches the silhouette style of the training data,
             independent of lighting/skin tone)
         -> GestureNet -> temporal smoothing + confidence gate

A gesture is only emitted when the same class wins on most of the last
WINDOW frames AND its mean confidence clears TAU — mirroring the
early-exit / tau-threshold design in the thesis.

Keys:  ESC quit
"""

from collections import deque

import cv2
import numpy as np
import torch
import mediapipe as mp

from gesture_net import (CLASSES, NONE, load_model, render_silhouette,
                         silhouette_to_tensor)

MODEL_PATH = "gesture3_model.pth"
TAU = 0.80          # mean confidence threshold for committing to a gesture
WINDOW = 7          # smoothing window (frames)
MIN_VOTES = 4       # frames in the window that must agree

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = load_model(MODEL_PATH, device)
print("Model loaded. Press ESC to exit.")

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                       min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

history = deque(maxlen=WINDOW)   # (class_idx, confidence)

COLORS = {"grab": (0, 140, 255), "drop": (0, 255, 0), "none": (160, 160, 160)}

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise SystemExit("Cannot open camera")

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    label, conf = "none", 0.0
    if result.multi_hand_landmarks:
        lm = result.multi_hand_landmarks[0]
        mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)

        pts = np.array([[p.x * w, p.y * h] for p in lm.landmark], np.float32)

        mask = render_silhouette(pts)
        with torch.no_grad():
            probs = torch.softmax(model(silhouette_to_tensor(mask).to(device)), 1)[0]
        idx = int(probs.argmax())
        history.append((idx, float(probs[idx])))

        # temporal smoothing + confidence gate
        votes = [c for c, _ in history]
        top = max(set(votes), key=votes.count)
        top_confs = [p for c, p in history if c == top]
        mean_conf = float(np.mean(top_confs))
        if (top != NONE and votes.count(top) >= MIN_VOTES
                and mean_conf >= TAU):
            label, conf = CLASSES[top], mean_conf
        else:
            label, conf = "none", float(probs[NONE])

        # gate debug: why is / isn't the big label committing?
        cv2.putText(frame,
                    f"gate: {CLASSES[top]} votes {votes.count(top)}/{len(history)}"
                    f" (need {MIN_VOTES})  avg {mean_conf:.2f} (need {TAU:.2f})",
                    (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)

        # debug overlays: silhouette preview + per-class probabilities
        preview = cv2.cvtColor(cv2.resize(mask, (120, 120)), cv2.COLOR_GRAY2BGR)
        frame[10:130, w - 130:w - 10] = preview
        for i, c in enumerate(CLASSES):
            cv2.putText(frame, f"{c}: {float(probs[i]):.2f}",
                        (10, h - 70 + i * 22), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, COLORS[c], 2)
    else:
        history.clear()

    color = COLORS[label]
    cv2.putText(frame, f"{label.upper()}  ({conf:.2f})", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)

    cv2.imshow("Grab / Drop Detector", frame)
    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()
