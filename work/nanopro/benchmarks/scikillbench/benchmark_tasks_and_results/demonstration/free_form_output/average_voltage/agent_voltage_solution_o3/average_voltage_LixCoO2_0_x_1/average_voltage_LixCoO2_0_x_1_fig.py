# Modified from agent's solution: adjusted font family and sizes for publication
import matplotlib
matplotlib.use("Agg")     # comment out to show an on-screen window
import matplotlib.pyplot as plt

# Use Arial font and larger text sizes
plt.rcParams["font.family"]      = "Arial"
plt.rcParams["font.size"]        = 12   # base
plt.rcParams["axes.labelsize"]   = 18   # x/y label
plt.rcParams["xtick.labelsize"]  = 14   # x ticks
plt.rcParams["ytick.labelsize"]  = 14   # y ticks
plt.rcParams["mathtext.fontset"] = "custom"
plt.rcParams["mathtext.rm"]      = "Arial"
plt.rcParams["mathtext.default"] = "rm"

# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------
models   = ["MF-ompa\nMPtrj+sAlex",
            "MF-ompa\nOMat24",
            "MF-0\nPBE (+U)",
            "MF-0\nr²SCAN"]
voltages = [3.368, 3.704, 3.377, 4.078]   # V
colors   = ["skyblue", "salmon", "lightgreen", "plum"]

# ----------------------------------------------------------------------
# Plot
# ----------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6, 4))
bars = ax.bar(models, voltages, color=colors, edgecolor="black", zorder=2)

# Reference line at 4.21 V
ref_v = 4.21
ax.axhline(ref_v, color="black", linewidth=2, zorder=1)

# Axes styling
ax.set_ylabel("Average Voltage (V)")
ax.set_ylim(0, 4.6)                           # some head-room
# Add 4.21 as a y-axis tick label
yticks = [0, 1, 2, 3, 4, ref_v, 4.6]
ax.set_yticks(yticks)
ax.set_yticklabels(['0', '1', '2', '3', '4', '4.21', '4.6'])

ax.set_title(
    r"$\mathrm{LiCoO_2} \rightarrow \mathrm{CoO_2} + \mathrm{Li}$  (Co3+/Co4+ couple)",
    fontsize=19,
    pad=10,
)

# Numeric labels inside bars (top-center, slightly below the top)
for rect, v in zip(bars, voltages):
    ax.text(rect.get_x() + rect.get_width()/2,
            v - 0.05,                         # 0.05 V below the bar top
            f"{v:.2f}",
            ha="center", va="top", fontsize=14, color="black")

# ----------------------------------------------------------------------
plt.tight_layout()
plt.savefig("average_voltage_models_labeled.png", dpi=300)
print("Saved figure as average_voltage_LixCoO2_0_x_1_models_labeled.png")