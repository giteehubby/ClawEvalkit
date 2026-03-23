# Fixed and enhanced PEIS analysis code
import os
import json
import math
import time
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution
from impedance.models.circuits import CustomCircuit
from impedance.validation import rmse

# Start timing
_start_time = time.time()


def load_peis(path: str):
    """Load PEIS data (JSON or CSV) and return f, Z, height_cm, diameter_cm."""
    if path is None or not os.path.exists(path):
        raise FileNotFoundError(f"PEIS data file '{path}' not found")

    ext = os.path.splitext(path)[1].lower()
    frequencies = Z = height_cm = diameter_cm = None

    # --- JSON (MP experiment style) ----------------------------------------
    if ext == ".json":
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                obj = json.load(f)
            if isinstance(obj, list):  # some files wrap dict in list
                obj = obj[0]

            # dimensions (stored in mm)
            if "sample_height_mm" in obj:
                height_cm = float(obj["sample_height_mm"]) / 10.0
            if "sample_diameter_mm" in obj:
                diameter_cm = float(obj["sample_diameter_mm"]) / 10.0

            data = obj.get("data", {})
            freq_key = next((k for k in data if "frequency" in k.lower()), None)
            if freq_key:
                frequencies = np.asarray(data[freq_key], dtype=float)

            # modulus + phase preferred
            mod_key = next((k for k in data if "impedance modulus" in k.lower()), None)
            phase_key = next((k for k in data if "impedance phase" in k.lower()), None)
            if mod_key and phase_key:
                modulus = np.asarray(data[mod_key], dtype=float)
                phase = np.asarray(data[phase_key], dtype=float) # radians
                Z = modulus * (np.cos(phase) + 1j * np.sin(phase))
            else:  # real + imag fallback
                real_key = next((k for k in data if "zreal" in k.lower()), None)
                imag_key = next((k for k in data if "zimag" in k.lower()), None)
                if real_key and imag_key:
                    Z = np.asarray(data[real_key], dtype=float) + 1j * np.asarray(data[imag_key], dtype=float)

            if frequencies is not None and Z is not None:
                return frequencies, Z, height_cm, diameter_cm
        except Exception as e:
            warnings.warn(f"JSON loading failed: {e}")

    # --- CSV / TXT ----------------------------------------------------------
    try:
        df = pd.read_csv(path, comment="#")
        # dimensions from columns
        for col in df.columns:
            lc = col.lower()
            if lc in ["sample_height", "height", "height_cm"]:
                height_cm = float(df[col].dropna().iloc[0])
            if lc in ["sample_diameter", "diameter", "diameter_cm"]:
                diameter_cm = float(df[col].dropna().iloc[0])

        # dimensions from header comments
        if height_cm is None or diameter_cm is None:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    if line.strip().startswith("#"):
                        for seg in line.strip("#\n ").split(","):
                            if "=" in seg:
                                k, v = [s.strip().lower() for s in seg.split("=", 1)]
                                if k in ["height_cm", "height"]:
                                    height_cm = float(v)
                                if k in ["diameter_cm", "diameter"]:
                                    diameter_cm = float(v)

        # impedance columns (flexible names)
        def find(poss):
            for c in df.columns:
                if c.strip().lower() in poss:
                    return c
            return None

        f_col = find(["frequency", "freq", "f"])
        re_col = find(["zreal", "z_real", "real", "re"])
        im_col = find(["zimag", "z_imag", "imag", "im", "-im"])
        if None in [f_col, re_col, im_col]:
            raise ValueError("Frequency/Real/Imag columns not found in CSV data.")

        frequencies = df[f_col].astype(float).to_numpy()
        Z = df[re_col].astype(float).to_numpy() + 1j * df[im_col].astype(float).to_numpy()
        return frequencies, Z, height_cm, diameter_cm
    except Exception as e:
        raise RuntimeError(f"Could not load PEIS file: {e}")


# --------------------------- Main analysis -----------------------------------
PATH = os.getenv("PEIS_DATA_PATH")
frequencies, Z, height_cm, diameter_cm = load_peis(PATH)
if height_cm is None or diameter_cm is None:
    raise ValueError("Sample height and diameter could not be determined from data file.")

# sort ascending (required by impedance.py)
if not np.all(np.diff(frequencies) > 0):
    order = np.argsort(frequencies)
    frequencies = frequencies[order]
    Z = Z[order]

# Equivalent circuit: CPE1-p(CPE2,R1)
CIRCUIT_STR = "CPE1-p(CPE2,R1)"
param_names = ["Q1", "n1", "Q2", "n2", "R1"]

bounds = [
    (1e-9, 1.0),   # Q1
    (0.0, 1.0),    # n1
    (1e-9, 1.0),   # Q2
    (0.0, 1.0),    # n2
    (1e-3, 1e6),   # R1
]

# Global optimisation (differential evolution)
print("Running global optimisation (differential evolution) ...")

def obj(theta):
    try:
        circ = CustomCircuit(CIRCUIT_STR, initial_guess=list(theta))
        return np.mean(np.abs(circ.predict(frequencies) - Z))
    except Exception:
        return 1e20

res = differential_evolution(obj, bounds, strategy="best1bin", maxiter=500, tol=1e-5, polish=True)
initial_guess = list(res.x)
print("Initial parameter guesses:")
for n, v in zip(param_names, initial_guess):
    print(f"  {n:>3s} = {v:.4g}")

# Local least-squares fit
circuit = CustomCircuit(CIRCUIT_STR, initial_guess=initial_guess)
circuit.fit(frequencies, Z)
print("\nFitted circuit parameters:")
print(circuit)

# Extract R1
names, _ = circuit.get_param_names()  # (names, units)
R1_ohm = dict(zip(names, circuit.parameters_)).get("R1")
if R1_ohm is None:
    raise RuntimeError("R1 not found in fitted parameters.")

# Ionic conductivity (S/cm)
area_cm2 = math.pi * (diameter_cm / 2.0) ** 2
sigma_S_per_cm = height_cm / (R1_ohm * area_cm2)
print("\n===========================================")
print(f"Ionic conductivity: {sigma_S_per_cm:.4e} S/cm")
print("===========================================")

# End timing (before plotting)
_elapsed_time = time.time() - _start_time

# The following code is written by us to generate a Nyquist plot to see if the fit is good
# -----------------------------------------------------------------------------
# Plot Nyquist plot with measured and fitted data
# -----------------------------------------------------------------------------
import matplotlib.pyplot as plt

# Set Arial font and larger font sizes
plt.rcParams['font.family'] = 'Arial'
plt.rcParams['font.size'] = 20  # Base font size
plt.rcParams['axes.labelsize'] = 24  # x and y axis labels
plt.rcParams['axes.titlesize'] = 24  # Title
plt.rcParams['xtick.labelsize'] = 18  # x-axis tick labels
plt.rcParams['ytick.labelsize'] = 18  # y-axis tick labels
plt.rcParams['legend.fontsize'] = 24  # Legend
plt.rcParams['figure.titlesize'] = 24  # Figure title

# Generate fitted impedance
Z_fit = circuit.predict(frequencies)

# Create Nyquist plot
plt.figure(figsize=(8, 6))
plt.plot(Z.real, -Z.imag, 'bo', label='Measured', markersize=4)
plt.plot(Z_fit.real, -Z_fit.imag, 'r-', label='Fitted', linewidth=2)
plt.xlabel("Z' (Ω)", fontsize=24)
plt.ylabel("-Z'' (Ω)", fontsize=24)
# plt.title("Nyquist Plot - Measured vs Fitted", fontsize=20)
plt.grid(True, alpha=0.3)
plt.legend(fontsize=24)
plt.axis('equal')

# Save plot as SVG
plot_name = f"nyquist_plot.svg"
plt.savefig(plot_name, bbox_inches='tight')
plt.close()
print(f"Nyquist plot saved as {os.path.abspath(plot_name)}")

# Calculate and output metrics
# Calculate fit quality metrics
_rmse = rmse(Z, Z_fit)
_ss_res = np.sum(np.abs(Z - Z_fit) ** 2)
_ss_tot = np.sum(np.abs(Z - np.mean(Z)) ** 2)
_r2 = 1 - _ss_res / _ss_tot

print("\n" + "=" * 50)
print("PERFORMANCE METRICS")
print("=" * 50)
print(f"Runtime:  {_elapsed_time:.2f} s")
print(f"RMSE:     {_rmse:.4e}")
print(f"R²:       {_r2:.6f}")
print("=" * 50)