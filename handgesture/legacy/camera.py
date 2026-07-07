import cv2
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
import mediapipe as mp

# ===========================
# Class Names
# ===========================

classes = [
    '0','1','10','11','12','13','14','15','16','17',
    '18','19','2','3','4','5','6','7','8','9'
]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ===========================
# Image Transform
# ===========================

transform = transforms.Compose([
    transforms.Resize((40,40)),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485,0.456,0.406],
        [0.229,0.224,0.225]
    )
])
# ===========================
# CNN Model
# ===========================

class CnnModel(nn.Module):

    def __init__(self):
        super().__init__()

        self.network = nn.Sequential(

            nn.Conv2d(3,100,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.Conv2d(100,150,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.MaxPool2d(2,2),

            nn.Conv2d(150,200,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.Conv2d(200,200,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.MaxPool2d(2,2),

            nn.Conv2d(200,250,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.Conv2d(250,250,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.MaxPool2d(2,2),

            nn.Flatten(),

            nn.Linear(6250,256),
            nn.ReLU(),

            nn.Linear(256,128),
            nn.ReLU(),

            nn.Linear(128,64),
            nn.ReLU(),

            nn.Linear(64,32),
            nn.ReLU(),

            nn.Dropout(0.25),

            nn.Linear(32,20)

        )

    def forward(self,x):
        return self.network(x)


# ===========================
# Load Trained Model
# ===========================

model = CnnModel().to(device)

model.load_state_dict(
    torch.load(
        "gesture_model.pth",
        map_location=device
    )
)

model.eval()

print("Model Loaded Successfully!")

# ===========================
# MediaPipe Setup
# ===========================

mp_hands = mp.solutions.hands

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

mp_draw = mp.solutions.drawing_utils


# ===========================
# Webcam Start
# ===========================

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Cannot open camera")
    exit()


print("Press ESC to Exit")

while True:

    success, frame = cap.read()

    if not success:
        break

    frame = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    result = hands.process(rgb)

    if result.multi_hand_landmarks:

        for hand_landmarks in result.multi_hand_landmarks:

            mp_draw.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS
            )

            h, w, c = frame.shape

            x_list = []
            y_list = []

            for lm in hand_landmarks.landmark:

                x_list.append(int(lm.x * w))
                y_list.append(int(lm.y * h))

            x1 = max(min(x_list)-20,0)
            y1 = max(min(y_list)-20,0)

            x2 = min(max(x_list)+20,w)
            y2 = min(max(y_list)+20,h)

            hand = frame[y1:y2, x1:x2]

            if hand.size == 0:
                continue
                        # ===========================
            # Image Preprocessing
            # ===========================

            image = cv2.cvtColor(hand, cv2.COLOR_BGR2RGB)

            image = Image.fromarray(image)

            image = transform(image)

            image = image.unsqueeze(0).to(device)

            # ===========================
            # Prediction
            # ===========================

            with torch.no_grad():

                output = model(image)

                _, pred = torch.max(output,1)

                gesture = classes[pred.item()]

            # ===========================
            # Show Prediction
            # ===========================

            cv2.rectangle(
                frame,
                (x1,y1),
                (x2,y2),
                (0,255,0),
                2
            )

            cv2.putText(
                frame,
                f"Gesture : {gesture}",
                (x1,y1-10),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0,255,0),
                2
            )

    cv2.imshow("Hand Gesture Recognition", frame)

    key = cv2.waitKey(1)

    if key == 27:      # ESC key
        break

cap.release()

cv2.destroyAllWindows()