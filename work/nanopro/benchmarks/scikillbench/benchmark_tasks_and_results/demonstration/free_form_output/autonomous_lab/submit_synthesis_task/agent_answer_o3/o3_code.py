# Li2Fe0.8Ni0.2Cl4 autonomous synthesis submission
# -------------------------------------------------
#   • runs in simulation mode (SIM_MODE_FLAG = TRUE)
#   • uses alab_gpss + AlabOS (alab_management)
#   • falls back to a hand-coded stoichiometric recipe if alab_gpss
#     cannot auto-balance the reaction
# -------------------------------------------------
import os
import sys
import importlib

# ---------------------------------------------------------------------------
# 1)  Environment – simulation / config paths
# ---------------------------------------------------------------------------
os.environ["SIM_MODE_FLAG"] = "TRUE"                       # dry-run
if "ALABOS_CONFIG_PATH" in os.environ:                    # propagate existing cfg
    os.environ["ALABOS_CONFIG_PATH"] = os.getenv("ALABOS_CONFIG_PATH")

# ---------------------------------------------------------------------------
# 2)  Make sure the in-house alab_gpss repository is importable
# ---------------------------------------------------------------------------
repo_path = os.getenv("ALAB_GPSS_FILE_PATH", "")
for p in (repo_path, os.path.join(repo_path, "src")):
    if p and os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# 3)  Import alab-gpss helpers – recipe generator (with graceful fallback)
# ---------------------------------------------------------------------------
try:
    balance_mod = importlib.import_module("alab_gpss.experiment_design.reactions.balance")
    generate_recipe = balance_mod.generate_recipe  # type: ignore[attr-defined]
except Exception as exc:  # pragma: no cover
    raise RuntimeError("alab_gpss not importable – check ALAB_GPSS_FILE_PATH") from exc

TARGET_FORMULA = "Li2Fe0.8Ni0.2Cl4"
PRECURSORS = ["LiCl", "FeCl2", "NiCl2"]      # simple chloride route
TARGET_MASS_G = 0.5

# first try alab-gpss automatic balancer
try:
    recipe = generate_recipe(TARGET_FORMULA, PRECURSORS, target_mass_g=TARGET_MASS_G)
except Exception:  # balancer failed – fall back to manual stoichiometry
    # -------------------------------------------------------------------
    # Li2Fe0.8Ni0.2Cl4 ⇨ use LiCl, FeCl2, NiCl2 in the same Li/Fe/Ni ratio
    #   LiCl   – provides 1 Li  &  1 Cl  → need   2 × LiCl per f.u.
    #   FeCl2  – provides Fe & 2 Cl       → need 0.8 × FeCl2
    #   NiCl2  – provides Ni & 2 Cl       → need 0.2 × NiCl2
    # -------------------------------------------------------------------
    MOLAR_MASS = {
        "LiCl": 6.941 + 35.453,          # = 42.394 g/mol
        "FeCl2": 55.845 + 2 * 35.453,    # = 126.751 g/mol
        "NiCl2": 58.693 + 2 * 35.453,    # = 129.599 g/mol
    }
    # stoichiometric coefficients
    coeff = {"LiCl": 2, "FeCl2": 0.8, "NiCl2": 0.2}
    mass_per_mole = sum(MOLAR_MASS[c] * coeff[c] for c in coeff)
    scale = TARGET_MASS_G / mass_per_mole
    class DummyPrecursor:
        def __init__(self, name, mass):
            self.name = name; self.mass = mass
    recipe = type("FallbackRecipe", (), {
        "precursors": [DummyPrecursor(n, MOLAR_MASS[n] * coeff[n] * scale) for n in coeff]
    })()

print("[INFO] Recipe prepared – precursor masses (g):")
for p in recipe.precursors:
    print(f"    {p.name:6s} : {p.mass:.6f}")

# ---------------------------------------------------------------------------
# 4)  Import Alab Management ExperimentBuilder + GPSS system tasks
# ---------------------------------------------------------------------------
from alab_management.builders.experimentbuilder import ExperimentBuilder
from alab_gpss.system.tasks.add_sample import GPSSAddSample
from alab_gpss.system.tasks.powder_dispensing import GPSSPowderDispensing
from alab_gpss.system.tasks.powder_mixing import GPSSPowderMixing
from alab_gpss.system.tasks.heating import GPSSHeating
from alab_gpss.system.tasks.sample_grinding_xrd import GPSSSampleGrindingXRD
from alab_gpss.system.tasks.remove_sample import RemoveSample

# ---------------------------------------------------------------------------
# 5)  Assemble the autonomous workflow
# ---------------------------------------------------------------------------
exp = ExperimentBuilder(name="Li2Fe0.8Ni0.2Cl4_synthesis")

sample = exp.add_sample(name="Li2Fe0.8Ni0.2Cl4_sample")

# (i)  sample registration (barcode etc.)
GPSSAddSample(notify_user=False).add_to(sample)

# (ii) Powder dispensing (4 balls)
chem_masses = {p.name: p.mass for p in recipe.precursors}
GPSSPowderDispensing(chemical_list=chem_masses, tolerance_percent=1, num_balls=4).add_to(sample)

# (iii) Two-stage milling 1 kRPM & 1.5 kRPM (5 min each, 30 s breaks)
GPSSPowderMixing(speed=[1000, 1500], duration_seconds=[300, 300], interval_seconds=30).add_to(sample)

# (iv) Calcination 450 °C, ramp 2 °C/min, 12 h soak
GPSSHeating(heating_profile=[(450, 2, 60 * 12)]).add_to(sample)

# (v) Post-grinding for XRD (6 min @ 28 Hz)
GPSSSampleGrindingXRD(grinding_time_sec=360, frequency=28).add_to(sample)

# (vi) Sample removal / storage hand-off
RemoveSample().add_to(sample)

# ---------------------------------------------------------------------------
# 6)  Submit to the (simulated) AlabOS scheduler
# ---------------------------------------------------------------------------
tracking_id = exp.submit()            # default localhost / dry-run
print("[SUCCESS] Experiment submitted – tracking ID:", tracking_id)