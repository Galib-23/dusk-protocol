"""
Shared definitions for the 3-class (grab / drop / none) gesture model.

The dataset is 50x50 binary hand silhouettes (hand = white, background = black)
in 20 numbered folders. We remap them to 3 classes:

    grab : closed fist               -> source folders 11, 14, 16
    drop : fully open / spread hand  -> source folders 4, 5
    none : every other pose          -> all remaining folders

Keeping near-misses (four fingers, thumbs-up, OK sign, ...) inside "none"
forces the model to learn a tight boundary around grab/drop, which is what
gives high precision.
"""

import cv2
import numpy as np
import torch
import torch.nn as nn

# ===========================
# Classes and remapping
# ===========================

CLASSES = ["grab", "drop", "none"]
GRAB, DROP, NONE = 0, 1, 2

GRAB_SOURCE = {"11", "14", "16"}   # solid fists, different angles
DROP_SOURCE = {"4", "5"}           # fully spread open hand


def remap_class(folder_name: str) -> int:
    if folder_name in GRAB_SOURCE:
        return GRAB
    if folder_name in DROP_SOURCE:
        return DROP
    return NONE


# ===========================
# Preprocessing
# ===========================

IMG_SIZE = 64
BIN_THRESHOLD = 0.5  # after ToTensor (0..1); hand -> 1, background -> 0


def binarize(t: torch.Tensor) -> torch.Tensor:
    return (t > BIN_THRESHOLD).float()


# ===========================
# Model
# ===========================

class GestureNet(nn.Module):
    """Small BN + global-average-pooling CNN (~0.3M params) for 64x64 binary masks."""

    def __init__(self, num_classes: int = len(CLASSES)):
        super().__init__()

        def block(cin, cout):
            return [
                nn.Conv2d(cin, cout, 3, padding=1, bias=False),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
            ]

        self.features = nn.Sequential(
            *block(1, 32),
            *block(32, 32),
            nn.MaxPool2d(2),            # 32x32
            *block(32, 64),
            *block(64, 64),
            nn.MaxPool2d(2),            # 16x16
            *block(64, 128),
            nn.MaxPool2d(2),            # 8x8
            *block(128, 128),
            nn.AdaptiveAvgPool2d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def load_model(path: str, device) -> GestureNet:
    ckpt = torch.load(path, map_location=device)
    model = GestureNet(num_classes=len(ckpt.get("classes", CLASSES)))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    return model


# ===========================
# Landmark -> silhouette rendering
# ===========================
# The training images are segmentation-style silhouettes, but a live camera
# gives an RGB crop. Instead of fragile skin segmentation, we draw a filled
# hand silhouette from the 21 MediaPipe landmarks: a filled palm polygon plus
# thick capsules along each finger. Lighting-independent by construction.

_FINGERS = [
    [1, 2, 3, 4],        # thumb
    [5, 6, 7, 8],        # index
    [9, 10, 11, 12],     # middle
    [13, 14, 15, 16],    # ring
    [17, 18, 19, 20],    # pinky
]
_PALM = [0, 1, 2, 5, 9, 13, 17]


def render_silhouette(landmarks_xy: np.ndarray, size: int = 200,
                      thickness_scale: float = 0.28, forearm: bool = True,
                      forearm_width: float = 1.05, close: bool = True) -> np.ndarray:
    """
    landmarks_xy: (21, 2) array of landmark positions in any consistent
    pixel/unit space. Returns a (size, size) uint8 mask, hand=255, bg=0.

    A forearm stub is drawn from the wrist to the canvas edge because the
    training silhouettes all include one — without it a fist renders as a
    small floating blob and is not recognized.
    """
    pts = np.asarray(landmarks_xy, dtype=np.float32).copy()

    # Fit into the canvas with a margin, preserving aspect ratio
    mn, mx = pts.min(axis=0), pts.max(axis=0)
    span = float(max(mx[0] - mn[0], mx[1] - mn[1], 1e-6))
    margin = 0.18 * size
    pts = (pts - mn) / span * (size - 2 * margin) + margin
    # center the shorter axis
    extent = pts.max(axis=0) - pts.min(axis=0)
    pts += (size - 2 * margin - extent) / 2

    ipts = pts.astype(np.int32)
    canvas = np.zeros((size, size), np.uint8)

    palm_width = float(np.linalg.norm(pts[5] - pts[17])) + 1e-6
    thickness = max(3, int(thickness_scale * palm_width))

    if forearm:
        # extend away from the palm (wrist -> beyond canvas edge; cv2 clips)
        d = pts[0] - pts[9]
        d = d / (np.linalg.norm(d) + 1e-6)
        end = (pts[0] + d * size * 1.5).astype(np.int32)
        cv2.line(canvas, tuple(ipts[0]), tuple(end), 255,
                 thickness=max(3, int(forearm_width * palm_width)))

    hull = cv2.convexHull(ipts[_PALM])
    cv2.fillConvexPoly(canvas, hull, 255)

    for finger in _FINGERS:
        chain = ipts[[0] + finger]
        cv2.polylines(canvas, [chain], False, 255, thickness=thickness,
                      lineType=cv2.LINE_8)
        for j in finger:
            cv2.circle(canvas, tuple(ipts[j]), thickness // 2, 255, -1)

    if close:
        # merge the gaps between folded fingers into a solid fist blob;
        # kernel is small enough to leave spread fingers separated
        k = max(3, (thickness // 2) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        canvas = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, kernel)

    return canvas


def silhouette_to_tensor(mask: np.ndarray) -> torch.Tensor:
    """(H, W) uint8 mask -> (1, 1, IMG_SIZE, IMG_SIZE) float tensor in {0, 1}."""
    m = cv2.resize(mask, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
    t = torch.from_numpy(m).float().div_(255.0)
    return binarize(t).unsqueeze(0).unsqueeze(0)
