"""
Export gesture_temporal.pth to a plain-JSON weight file that the Android/web
app's ~60-line JavaScript GRU implementation can load — no ML runtime needed.

Usage:  python export_gru_json.py [output.json]
"""

import json
import os
import sys

import torch

from gesture_net import CLASSES

CKPT_PATH = os.path.join(os.path.dirname(__file__), "gesture_temporal.pth")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "gesture_temporal.json")


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    ckpt = torch.load(CKPT_PATH, map_location="cpu")
    sd = ckpt["state_dict"]

    w_ih = sd["gru.weight_ih_l0"]           # (3H, F) rows ordered [r | z | n]
    hidden = w_ih.shape[0] // 3

    data = {
        "classes": ckpt["classes"],
        "exits": list(ckpt["exits"]),
        "temps": [float(t) for t in ckpt["temps"]],
        "hidden": hidden,
        "inputDim": w_ih.shape[1],
        "w_ih": w_ih.tolist(),
        "w_hh": sd["gru.weight_hh_l0"].tolist(),
        "b_ih": sd["gru.bias_ih_l0"].tolist(),
        "b_hh": sd["gru.bias_hh_l0"].tolist(),
        "heads": [{"w": sd[f"heads.{i}.weight"].tolist(),
                   "b": sd[f"heads.{i}.bias"].tolist()}
                  for i in range(len(ckpt["exits"]))],
    }
    assert data["classes"] == CLASSES

    with open(out_path, "w") as f:
        json.dump(data, f)
    print(f"exported {os.path.getsize(out_path) / 1e6:.2f} MB -> {out_path}")


if __name__ == "__main__":
    main()
