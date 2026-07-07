"""
Generate all thesis figures into docs/figures/.

Real data sources: the live metrics DB (camera duty), the temporal model's
tau sweep CSV, recorded training results, and the synthetic-data preview
images. The battery figure is a SIMULATED PROJECTION from measured duty
cycles under stated assumptions — labeled as such wherever it is used.
"""

import csv
import os
import shutil
import sys
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
HG = os.path.join(HERE, "..", "handgesture")
os.makedirs(FIG, exist_ok=True)

sys.path.insert(0, os.path.join(HERE, "..", "measurements"))

ALWAYS_C, DUSK_C = "#c0392b", "#3f51b5"

# ---------------------------------------------------------------- live duty
def duty_from_db():
    """Returns (duty_always_pct, duty_dusk_pct, n_always, n_dusk, table)."""
    try:
        from analyze_logs import load_rows, split_sessions, analyze
        class A: url = "https://pd.brittoo.xyz/logs.csv"; csv = None
        rows = load_rows(A)
        table = analyze(split_sessions(rows))
        agg = {}
        for m in ("always", "dusk"):
            rs = [r for r in table if r["mode"] == m]
            if rs:
                agg[m] = (sum(r["duty_pct"] for r in rs) / len(rs), len(rs))
        return (agg.get("always", (93.0, 4))[0], agg.get("dusk", (17.1, 3))[0],
                agg.get("always", (0, 4))[1], agg.get("dusk", (0, 3))[1], table)
    except Exception as e:
        print("live fetch failed, using snapshot:", e)
        return 93.0, 17.1, 4, 3, []


DUTY_ALWAYS, DUTY_DUSK, N_ALWAYS, N_DUSK, SESSION_TABLE = duty_from_db()

# ------------------------------------------------------------- architecture
def fig_architecture():
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.axis("off")

    def box(x, y, w, h, text, fc="#eef1fb", ec="#3f51b5"):
        ax.add_patch(plt.Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.5,
                                   zorder=2, joinstyle="round"))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=9, zorder=3)

    def arrow(x1, y1, x2, y2, label=None):
        ax.annotate("", (x2, y2), (x1, y1),
                    arrowprops=dict(arrowstyle="->", lw=1.4, color="#333"))
        if label:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.03, label,
                    ha="center", fontsize=8, color="#333")

    box(0.02, 0.55, 0.20, 0.30, "TIER 1\nproximity + light\nwave detector\n(rule-based, no ML)",
        fc="#fdf2e3", ec="#e67e22")
    box(0.30, 0.55, 0.17, 0.30, "Camera ON\nMediaPipe Hands\n21 landmarks")
    box(0.55, 0.55, 0.19, 0.30, "28 invariant\nfeatures / frame\n(dist. ratios + Δ)")
    box(0.02, 0.08, 0.30, 0.30, "Early-exit GRU (62k params)\nexit heads @ 4/8/12/16/24 frames\ncalibrated conf ≥ τ → COMMIT")
    box(0.44, 0.08, 0.14, 0.30, "Camera OFF\n(early exit)", fc="#e8f8f0", ec="#27ae60")
    box(0.66, 0.08, 0.135, 0.30, "grab / drop\nevent")
    box(0.855, 0.08, 0.125, 0.30, "pick & drop\nbackend", fc="#f4ecf7", ec="#8e44ad")
    box(0.80, 0.55, 0.18, 0.30, "Battery policy\nτ = f(battery%)\n(Phase 3)", fc="#fdecea", ec="#c0392b")

    arrow(0.22, 0.70, 0.30, 0.70, "wake")
    arrow(0.47, 0.70, 0.55, 0.70)
    arrow(0.645, 0.55, 0.32, 0.38)
    arrow(0.32, 0.23, 0.44, 0.23)
    arrow(0.58, 0.23, 0.66, 0.23)
    arrow(0.795, 0.23, 0.855, 0.23)
    arrow(0.87, 0.55, 0.30, 0.30)

    fig.savefig(os.path.join(FIG, "fig_architecture.png"),
                dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- duty bars
def fig_duty():
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    vals = [DUTY_ALWAYS, DUTY_DUSK]
    bars = ax.bar(["always-on", "Dusk (proximity-gated)"], vals,
                  color=[ALWAYS_C, DUSK_C], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.1f}%",
                ha="center", fontweight="bold")
    ax.set_ylabel("camera duty cycle (%)")
    ax.set_ylim(0, 108)
    ax.set_title(f"Measured camera-on time share "
                 f"({N_ALWAYS}+{N_DUSK} sessions)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_camera_duty.png"), dpi=200)
    plt.close(fig)


# ------------------------------------------------- battery projection (SIM)
D_BASE = 4.0          # assumed screen-on baseline, %/30 min
KAPPAS = [4.0, 6.0, 8.0]  # assumed camera+pipeline cost at 100% duty, %/30min

def sim_drain(duty_pct, kappa):
    return D_BASE + kappa * duty_pct / 100.0

def fig_battery_projection():
    t = np.linspace(0, 30, 61)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for duty, color, name in [(DUTY_ALWAYS, ALWAYS_C, "always-on"),
                              (DUTY_DUSK, DUSK_C, "Dusk")]:
        lo = 100 - sim_drain(duty, KAPPAS[0]) * t / 30
        hi = 100 - sim_drain(duty, KAPPAS[-1]) * t / 30
        mid = 100 - sim_drain(duty, KAPPAS[1]) * t / 30
        ax.fill_between(t, lo, hi, color=color, alpha=0.15)
        ax.plot(t, mid, color=color, lw=2.2,
                label=f"{name} (duty {duty:.0f}%)")
    ax.set_xlabel("session time (min)")
    ax.set_ylabel("battery (%)")
    ax.set_title("SIMULATED battery projection from measured duty cycles\n"
                 r"(band: camera-pipeline cost $\kappa$ = 4–8 %/30 min, "
                 f"baseline {D_BASE:.0f} %/30 min)")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_battery_projection.png"), dpi=200)
    plt.close(fig)
    mid_a = sim_drain(DUTY_ALWAYS, KAPPAS[1])
    mid_d = sim_drain(DUTY_DUSK, KAPPAS[1])
    return mid_a, mid_d, 100 * (mid_a - mid_d) / mid_a


# --------------------------------------------------------------- tau sweep
def fig_tau():
    rows = list(csv.DictReader(open(os.path.join(HG, "results_temporal.csv"))))
    taus = [float(r["tau"]) for r in rows]
    frames = [float(r["mean_frames"]) for r in rows]
    ff = [100 * float(r["false_fire"]) for r in rows]

    fig, ax1 = plt.subplots(figsize=(6.6, 3.9))
    ax1.plot(taus, frames, "o-", color=DUSK_C, lw=2)
    ax1.set_xlabel(r"exit confidence threshold $\tau$")
    ax1.set_ylabel("mean frames-to-decision", color=DUSK_C)
    ax1.axhline(24, color="gray", ls="--", lw=1)
    ax1.text(taus[0], 24.4, "no-early-exit baseline (24 frames)",
             fontsize=8, color="gray")
    ax1.set_ylim(12, 26)
    ax2 = ax1.twinx()
    ax2.plot(taus, ff, "s--", color=ALWAYS_C, lw=1.6)
    ax2.set_ylabel("false-fire rate on none (%)", color=ALWAYS_C)
    ax2.set_ylim(-0.05, 1.0)
    ax1.set_title("Early-exit operating curve (synthetic test, gesture acc. = 100% at all τ)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_tau_sweep.png"), dpi=200)
    plt.close(fig)
    return rows


# ------------------------------------------------------- per-head accuracy
HEAD_ACCS = [0.9989, 0.9991, 0.9986, 0.9989, 1.0000]
EXITS = [4, 8, 12, 16, 24]

def fig_heads():
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    ax.bar([f"k={k}" for k in EXITS], [100 * a for a in HEAD_ACCS],
           color=DUSK_C, width=0.6)
    ax.set_ylim(99, 100.05)
    ax.set_ylabel("anytime-label accuracy (%)")
    ax.set_xlabel("exit head (frames)")
    ax.set_title("Per-exit-head accuracy (synthetic test, n=3000)")
    for i, a in enumerate(HEAD_ACCS):
        ax.text(i, 100 * a + 0.005, f"{100 * a:.2f}", ha="center", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_head_acc.png"), dpi=200)
    plt.close(fig)


# --------------------------------------------------- static model confusion
def fig_confusion():
    cm = np.array([[497, 0, 3], [0, 498, 2], [4, 6, 490]])
    classes = ["grab", "drop", "none"]
    fig, ax = plt.subplots(figsize=(4.6, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(3), classes)
    ax.set_yticks(range(3), classes)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    for i in range(3):
        for j in range(3):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > 250 else "black")
    ax.set_title("Static model — landmark-render test\n(99.0% accuracy, n=1500)")
    fig.colorbar(im, shrink=0.8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_confusion_static.png"), dpi=200)
    plt.close(fig)


def fig_gantt():
    phases = [
        ("Literature review & feasibility", 0, 3),
        ("Static model + dataset remap", 2, 3),
        ("Synthetic hand generator", 4, 2),
        ("Landmark render pipeline", 5, 2),
        ("Temporal early-exit model", 6, 3),
        ("Web prototype + backend", 7, 2),
        ("Android app (two-tier)", 9, 3),
        ("Instrumentation + DB logging", 11, 2),
        ("Measurements & analysis", 12, 3),
        ("Battery A/B + policy", 14, 3),
        ("Real-sequence dataset", 14, 3),
        ("Thesis writing", 15, 3),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    for i, (name, start, dur) in enumerate(phases):
        ax.barh(i, dur, left=start, height=0.6,
                color=DUSK_C if i % 2 else "#7986cb")
    ax.set_yticks(range(len(phases)), [p[0] for p in phases], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("project week")
    ax.set_title("Work plan timeline")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_gantt.png"), dpi=200)
    plt.close(fig)


def copy_previews():
    shutil.copy(os.path.join(HG, "synth_preview.png"),
                os.path.join(FIG, "fig_synth_poses.png"))
    shutil.copy(os.path.join(HG, "synth_seq_preview.png"),
                os.path.join(FIG, "fig_synth_seq.png"))


def build_all():
    fig_architecture()
    fig_duty()
    proj = fig_battery_projection()
    tau_rows = fig_tau()
    fig_heads()
    fig_confusion()
    fig_gantt()
    copy_previews()
    print(f"figures -> {FIG}")
    return {"duty_always": DUTY_ALWAYS, "duty_dusk": DUTY_DUSK,
            "n_always": N_ALWAYS, "n_dusk": N_DUSK,
            "proj_always": proj[0], "proj_dusk": proj[1],
            "proj_saving": proj[2], "tau_rows": tau_rows,
            "session_table": SESSION_TABLE}


if __name__ == "__main__":
    build_all()
