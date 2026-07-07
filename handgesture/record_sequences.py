"""
Record real landmark sequences for the temporal model / Dusk dataset.

Keys (press them with the CAMERA WINDOW focused, not the terminal):
  g / d / n : select label (grab / drop / none)
  SPACE     : record — capture starts IMMEDIATELY ("GO!"), so just perform
              the gesture naturally; ~2.5 s of frames are captured and the
              training loader auto-centers on the motion afterwards
  ESC       : quit

Each take is saved to sequences/<label>/<timestamp>.npz with:
  landmarks (T, 21, 3) MediaPipe normalized coords, timestamps, label,
  frame_size (w, h) for aspect correction

Train with the real data mixed in:
  python train_temporal.py --real sequences
"""

import os
import time

import cv2
import numpy as np
import mediapipe as mp

from gesture_net import CLASSES

OUT_ROOT = os.path.join(os.path.dirname(__file__), "sequences")
RAW_FRAMES = 72          # ~2.5-3 s; loader resamples + crops to the model window

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                       min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)   # DSHOW: fast + reliable on Windows
if not cap.isOpened():
    cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise SystemExit("Cannot open camera — is another app (camera3.py, "
                     "camera_temporal.py, Zoom, ...) using it?")

WIN = "Sequence Recorder"
cv2.namedWindow(WIN)
try:
    cv2.setWindowProperty(WIN, cv2.WND_PROP_TOPMOST, 1)
except cv2.error:
    pass

label = 0
recording = False
frames, stamps = [], []
counts = {c: len(os.listdir(os.path.join(OUT_ROOT, c)))
          if os.path.isdir(os.path.join(OUT_ROOT, c)) else 0 for c in CLASSES}

print(__doc__)
print(f"Camera opened ({int(cap.get(3))}x{int(cap.get(4))}). "
      f"CLICK THE '{WIN}' WINDOW FIRST so it receives your key presses.")

while True:
    ok, frame = cap.read()
    if not ok:
        print("Camera stopped delivering frames — is another app using it? "
              "Close it and rerun.")
        break
    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    lm = result.multi_hand_landmarks[0] if result.multi_hand_landmarks else None
    if lm is not None:
        mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)

    if recording:
        if lm is not None:
            frames.append([[p.x, p.y, p.z] for p in lm.landmark])
            stamps.append(time.time())
            cv2.putText(frame, f"GO!  {len(frames)}/{RAW_FRAMES}", (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        else:
            cv2.putText(frame, "hand lost - counter paused!", (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        if len(frames) >= RAW_FRAMES:
            d = os.path.join(OUT_ROOT, CLASSES[label])
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, time.strftime("%Y%m%d_%H%M%S") +
                                f"_{int(time.time() * 1000) % 1000:03d}.npz")
            np.savez_compressed(path, landmarks=np.array(frames, np.float32),
                                timestamps=np.array(stamps), label=label,
                                frame_size=np.array([w, h]))
            counts[CLASSES[label]] += 1
            print(f"saved {path}")
            recording = False
    elif lm is None:
        cv2.putText(frame, "show your hand to the camera", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    status = "  ".join(f"{c}:{counts[c]}" for c in CLASSES)
    cv2.putText(frame, f"label: {CLASSES[label].upper()}   [{status}]",
                (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, "g/d/n = label   SPACE = record   ESC = quit",
                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    cv2.imshow(WIN, frame)
    key = cv2.waitKey(1) & 0xFF
    if key == 27:
        break
    if key in (ord("g"), ord("G")):
        label = 0
        print("label -> grab")
    elif key in (ord("d"), ord("D")):
        label = 1
        print("label -> drop")
    elif key in (ord("n"), ord("N")):
        label = 2
        print("label -> none")
    elif key == ord(" ") and not recording:
        recording, frames, stamps = True, [], []
        print(f"GO — perform '{CLASSES[label]}' now")

cap.release()
cv2.destroyAllWindows()
