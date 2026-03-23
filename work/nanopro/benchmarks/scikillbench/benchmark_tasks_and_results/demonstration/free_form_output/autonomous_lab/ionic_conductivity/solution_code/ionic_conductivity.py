from datetime import datetime
from pydantic import BaseModel
from impedance.models.circuits import CustomCircuit
from impedance.validation import rmse
import numpy as np
import os
import time
import matplotlib.pyplot as plt
from monty.serialization import loadfn
from functools import cached_property

# Start timing
_start_time = time.time()


class IonicConductivity(BaseModel):
    measurement_id: str
    timestamp: datetime
    filename: str
    sample_height_mm: float
    sample_diameter_mm: float
    data: dict[str, list[float]]

    def prepare_fitting_data(self):
        frequency = np.array(self.data["Frequency [Hz]"])
        Z = np.array(self.data["Impedance modulus"]) * np.cos(np.array(self.data["Impedance phase"])) + 1j * np.array(
            self.data["Impedance modulus"]
        ) * np.sin(np.array(self.data["Impedance phase"]))
        return frequency, Z

    @cached_property
    def fitting_impedance(self):
        from scipy.optimize import differential_evolution

        frequency, Z = self.prepare_fitting_data()

        # Define the objective function for black-box optimization
        def objective(params):
            # params: [CPE1, w1, CPE2, w2, R1]
            try:
                circuit = CustomCircuit("CPE1-p(CPE2, R1)", initial_guess=params)
                circuit.fit(frequency, Z)
                Z_fit = circuit.predict(frequency)
                # Use normalized RMSE as the objective
                rmse = np.sqrt(np.mean(np.abs((Z - Z_fit) / Z) ** 2))
                # Penalize if fit fails or returns nan
                if np.isnan(rmse) or np.isinf(rmse):
                    return 1e6
                return rmse
            except Exception:
                return 1e6

        # Reasonable bounds for the parameters (domain knowledge may improve these)
        bounds = [
            (1e-8, 1e-3),   # CPE1
            (0, 1.0),     # w1
            (1e-8, 1e-3),   # CPE2
            (0, 1.0),     # w2
            (1e-1, 1e5),    # R1
        ]

        # Run black-box optimization to find a good initial guess
        result = differential_evolution(objective, bounds, maxiter=10000, popsize=20, polish=True, disp=True, seed=42)
        best_guess = result.x
        print("Best initial guess from black-box optimization:", best_guess)

        # Now fit with the best initial guess
        circuit = CustomCircuit("CPE1-p(CPE2, R1)", initial_guess=best_guess)
        circuit.fit(frequency, Z)
        return circuit, None

    @cached_property
    def ionic_conductivity(self):
        return (
            1
            / self.fitting_impedance[0].parameters_[-1]
            * (self.sample_height_mm / 10)
            / (np.pi * (self.sample_diameter_mm / 20) ** 2)
        )

    def plot_nyquist(self, with_fitting=False):
        # Set Arial font and larger font sizes
        plt.rcParams['font.family'] = 'Arial'
        plt.rcParams['font.size'] = 20
        plt.rcParams['axes.labelsize'] = 24
        plt.rcParams['axes.titlesize'] = 24
        plt.rcParams['xtick.labelsize'] = 18
        plt.rcParams['ytick.labelsize'] = 18
        plt.rcParams['legend.fontsize'] = 24
        plt.rcParams['figure.titlesize'] = 24

        frequency, Z = self.prepare_fitting_data()

        plt.figure(figsize=(8, 6))
        plt.plot(Z.real, -Z.imag, 'bo', label='Measured', markersize=4)
        if with_fitting:
            circuit = self.fitting_impedance[0]
            Z_fit = circuit.predict(frequency)
            plt.plot(Z_fit.real, -Z_fit.imag, 'r-', label='Fitted', linewidth=2)
        plt.xlabel("Z' (Ω)", fontsize=24)
        plt.ylabel("-Z'' (Ω)", fontsize=24)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=24)
        plt.axis('equal')
        return plt.gcf()

# Load data - exactly like in the notebook
ionic_conductivity = loadfn(os.getenv("PEIS_DATA_PATH"))

# Calculate ionic conductivity
print("\nCalculating ionic conductivity...")
conductivity = ionic_conductivity[0].ionic_conductivity
print(f"Ionic Conductivity: {conductivity:.6e} S/cm")

# End timing (before plotting)
_elapsed_time = time.time() - _start_time

# Save Nyquist plot with fitting for visual comparison
try:
    # Plot with measured data and fitted curve
    _fig = ionic_conductivity[0].plot_nyquist(with_fitting=True)
    _fig.savefig(f"nyquist_plot.svg", bbox_inches="tight")
    import matplotlib.pyplot as _plt
    _plt.close(_fig)
    print(f"Saved plot: nyquist_plot.svg")
except Exception as _e:
    print(f"Warning: failed to save Nyquist plot: {_e}")

# Calculate and output metrics
_frequency, _Z = ionic_conductivity[0].prepare_fitting_data()
_circuit = ionic_conductivity[0].fitting_impedance[0]
_Z_fit = _circuit.predict(_frequency)

# Calculate fit quality metrics
_rmse = rmse(_Z, _Z_fit)
_ss_res = np.sum(np.abs(_Z - _Z_fit) ** 2)
_ss_tot = np.sum(np.abs(_Z - np.mean(_Z)) ** 2)
_r2 = 1 - _ss_res / _ss_tot

print("\n" + "=" * 50)
print("PERFORMANCE METRICS")
print("=" * 50)
print(f"Runtime:  {_elapsed_time:.2f} s")
print(f"RMSE:     {_rmse:.4e}")
print(f"R²:       {_r2:.6f}")
print("=" * 50)
