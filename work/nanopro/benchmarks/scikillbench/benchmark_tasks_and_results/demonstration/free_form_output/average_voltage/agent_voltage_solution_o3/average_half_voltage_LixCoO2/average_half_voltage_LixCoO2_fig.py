# Modified from agent's solution: adjusted font family and sizes for publication
import matplotlib.pyplot as plt

# ─── Data ───────────────────────────────────────────────────────────
labels   = ["MF-ompa MPtrj+sAlex", "MF-ompa OMat24",
            "MF-0  PBE(+U)",        "MF-0  r²SCAN"]
V_low    = [3.674, 4.028, 3.651, 4.691]     # 0 < x < 0.5
V_high   = [3.065, 3.380, 3.103, 3.465]     # 0.5 < x < 1

# mapping label → colour / style
style = {
    "MF-ompa MPtrj+sAlex": dict(color="tab:blue",   ls="-"),
    "MF-ompa OMat24":      dict(color="tab:blue",   ls="--"),
    "MF-0  PBE(+U)":         dict(color="tab:orange", ls="-"),
    "MF-0  r²SCAN":        dict(color="tab:orange", ls="--"),
}

# ─── Plot ───────────────────────────────────────────────────────────
# Use Arial font and larger text sizes
plt.rcParams["font.family"]      = "Arial"
plt.rcParams["font.size"]        = 12   # base
plt.rcParams["axes.labelsize"]   = 18   # x/y label
plt.rcParams["xtick.labelsize"]  = 14   # x ticks
plt.rcParams["ytick.labelsize"]  = 14   # y ticks
plt.rcParams["legend.fontsize"]  = 12   # legend (base, will override below if needed)

fig, ax = plt.subplots(figsize=(5, 3.8))
x_pts = [0.0, 0.5, 1.0]

for lab, v_lo, v_hi in zip(labels, V_low, V_high):
    s = style[lab]
    ax.step(x_pts[:2], [v_lo, v_lo], where="post", **s, lw=2)          # low plateau
    ax.step(x_pts[1:], [v_hi, v_hi], where="post", **s, lw=2, label=lab)  # high plateau

# experimental references
ax.hlines(4.33, 0.0, 0.5, colors="black", linewidth=1.5)
ax.hlines(3.96, 0.5, 1.0, colors="black", linewidth=1.5)

# axes
ax.set_xlim(0, 1)
ax.set_xticks([0, 0.5, 1])
# Use plain text so all characters are in the same (non-italic) Arial font
ax.set_xlabel("Li fraction x in LixCoO2", fontsize=18)

ax.set_ylim(2, 5.3)
ax.set_yticks([2, 3, 4, 5])
ax.set_ylabel("Average voltage (V)", fontsize=18)

ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
# Legend further towards the top-right corner to avoid overlapping the curves
ax.legend(frameon=False, fontsize=12, loc="upper right", bbox_to_anchor=(1.2, 1.0))

plt.tight_layout()
plt.savefig("average_half_voltage.png", dpi=300, bbox_inches="tight")
print("Saved: average_half_voltage.png")