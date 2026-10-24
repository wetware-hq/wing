#!/usr/bin/env python3
"""Figure 1 for memo.md: run-to-run movement of the Path A specificity margin.

Every value is measured, not modelled. The archived column is the panel.json
held in the repository; the live column is the panel.json produced by the
2026-10-24 resubmit of all 100 decoy refolds. Inputs and code were identical
between the two runs.

Run:  python3 memo_figure.py
Out:  memo_figure.png (300 dpi), memo_figure.pdf
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

# design_id, live, committed  (six decimal places, as measured)
DATA = [
    ("pres_rIVnI2qWY81pul3zHRrN", 0.163938, 0.085826),
    ("pres_xpto8wJvfrJQhLVH4Mvz", -0.035344, -0.086617),
    ("pres_KvvXtVa6yakB17EmB1Ge", -0.053100, 0.006154),
    ("pres_G3ZfGGLFJXddOc0vhQwO", -0.067108, 0.000278),
    ("pres_lppWP1t4ozGyw5s4gq3P", -0.113753, -0.071025),
    ("pres_JA4idjMYaE8EsQKrcb6K", -0.145400, -0.228469),
    ("pres_Bw8vknhmXJUg72L6CGAw", -0.234372, -0.218620),
    ("pres_PfYJkQdsLag9x1R5Pt6L", -0.313844, -0.431196),
    ("pres_B8eqLRLyLSgzkVbLyC7C", -0.481160, -0.434002),
    ("pres_2SOqXG5xbTO4FD4yB5so", -0.643219, -0.568671),
]

THRESHOLD = 0.15
MAX_SHIFT = 0.117352  # largest |live - committed|, pres_PfYJkQdsLag9x1R5Pt6L

BG = "#FAF8F4"      # off-white, not pure white
INK = "#1F1F1F"     # ink colour 1: archived run, text, rules
ACCENT = "#1B5A7A"  # ink colour 2: live run

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.edgecolor": INK,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

fig, ax = plt.subplots(figsize=(7.4, 5.0))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

n = len(DATA)
# Row 0 at the top; one spare row at the bottom carries the effect-size bracket.
ys = list(range(n))
bracket_y = n + 0.45

# Prespecified threshold: a single thin reference line, quiet but clear.
ax.axvline(THRESHOLD, color=INK, linewidth=0.9, zorder=1)
# Zero: fainter still, so the sign of each margin reads without a gridline set.
ax.axvline(0.0, color=INK, linewidth=0.5, alpha=0.25, zorder=1)

for y, (_design, live, committed) in zip(ys, DATA):
    ax.plot([committed, live], [y, y], color=INK, linewidth=0.8, alpha=0.55, zorder=2)
    ax.plot(
        committed, y, marker="o", markersize=5.5, markerfacecolor=BG,
        markeredgecolor=INK, markeredgewidth=1.0, linestyle="none", zorder=3,
    )
    ax.plot(
        live, y, marker="o", markersize=5.5, color=ACCENT,
        linestyle="none", zorder=4,
    )

# Direct labelling on the top row instead of a legend box.
top_live, top_committed = DATA[0][1], DATA[0][2]
ax.annotate(
    "archived", xy=(top_committed, 0), xytext=(top_committed - 0.048, -0.55),
    ha="center", va="bottom", fontsize=9, color=INK,
)
ax.annotate(
    "live", xy=(top_live, 0), xytext=(top_live, -0.55),
    ha="center", va="bottom", fontsize=9, color=ACCENT,
)
ax.annotate(
    "0.15 threshold", xy=(THRESHOLD, 0), xytext=(THRESHOLD, -1.25),
    ha="center", va="bottom", fontsize=9, color=INK,
)
ax.annotate(
    "crosses the threshold", xy=(top_live, 0), xytext=(top_live + 0.022, 0),
    ha="left", va="center", fontsize=9, color=ACCENT,
)

# The comparison the reader should not have to compute: the largest observed
# run-to-run shift laid against the 0 - 0.15 decision distance, same scale.
ax.plot([0, THRESHOLD], [bracket_y - 0.42, bracket_y - 0.42],
        color=INK, linewidth=0.9, solid_capstyle="butt")
ax.annotate(
    f"prespecified threshold, 0 to {THRESHOLD:.2f}",
    xy=(THRESHOLD / 2, bracket_y - 0.42), xytext=(THRESHOLD + 0.015, bracket_y - 0.42),
    ha="left", va="center", fontsize=9, color=INK,
)
ax.plot([0, MAX_SHIFT], [bracket_y + 0.22, bracket_y + 0.22],
        color=ACCENT, linewidth=2.2, solid_capstyle="butt")
ax.annotate(
    f"largest run-to-run shift, {MAX_SHIFT:.6f}",
    xy=(MAX_SHIFT / 2, bracket_y + 0.22), xytext=(THRESHOLD + 0.015, bracket_y + 0.22),
    ha="left", va="center", fontsize=9, color=ACCENT,
)

ax.set_yticks(ys)
ax.set_yticklabels([d.replace("pres_", "") for d, _l, _c in DATA], fontsize=9)
ax.set_ylim(bracket_y + 0.9, -1.55)

ax.set_xlim(-0.70, 0.34)
ax.set_xticks([-0.6, -0.4, -0.2, 0.0, 0.2])
ax.set_xticklabels(["-0.6", "-0.4", "-0.2", "0.0", "0.2"], fontsize=9)
ax.set_xlabel("Specificity margin", fontsize=10, labelpad=8)

for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_linewidth(0.8)
ax.tick_params(axis="y", length=0, pad=6)
ax.tick_params(axis="x", length=3, width=0.8)

fig.savefig("/workspace/memo_figure.png", dpi=300, bbox_inches="tight", facecolor=BG)
fig.savefig("/workspace/memo_figure.pdf", bbox_inches="tight", facecolor=BG)
print("wrote memo_figure.png and memo_figure.pdf")
