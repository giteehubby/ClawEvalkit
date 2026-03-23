"""
pip install "numpy<2" ase mp-api sevenn torch pymatgen scipy"
export MP_API_KEY=<YOUR_MP_KEY>
"""

import os, warnings
from mp_api.client import MPRester
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.transformations.advanced_transformations import (
    OrderDisorderedStructureTransformation,
)
from ase.filters import UnitCellFilter
from ase.optimize import BFGS
from sevenn.calculator import SevenNetCalculator

warnings.filterwarnings("ignore")
adaptor = AseAtomsAdaptor()
API_KEY = os.getenv("MP_API_KEY")

# ─── helper ────────────────────────────────────────────────────────
def fetch_structure(formula):
    with MPRester(API_KEY) as mpr:
        return mpr.materials.summary.search(
            formula=formula, energy_above_hull=(0, 0),
            fields=["structure"]
        )[0].structure


def sevennet_relax(atoms, model, modal, tag, steps=300, fmax=0.05):
    atoms = atoms.copy()
    atoms.calc = SevenNetCalculator(model=model, modal=modal, device="cpu")
    BFGS(UnitCellFilter(atoms), logfile=f"{tag}.log").run(fmax=fmax, steps=steps)
    return atoms.get_potential_energy()


# ─── 1. build super-cell & enumerate orderings once ────────────────
lco_uc = fetch_structure("LiCoO2")
lco_uc.add_oxidation_state_by_guess()

sup = lco_uc.copy()
sup.make_supercell([2, 2, 1])        # Li4Co4O8  (4 CoO2 units)
n_co = sup.composition["Co"]         # 4

for site in sup:
    if site.specie.symbol == "Li":
        site.species = {site.specie: 0.5}    # 50 % Li–vacancy

odt = OrderDisorderedStructureTransformation()
ordered_structs = [
    d["structure"] for d in odt.apply_transformation(sup, return_ranked_list=5)
]

li_bulk = fetch_structure("Li")

# ─── 2. loop over four SevenNet variants ───────────────────────────
variants = [
    ("MF-ompa  MPtrj+sAlex", "7net-mf-ompa", "mpa"),
    ("MF-ompa  OMat24",      "7net-mf-ompa", "omat24"),
    ("MF-0     PBE+U",       "7net-mf-0",    "PBE"),
    ("MF-0     r²SCAN",      "7net-mf-0",    "R2SCAN"),
]

summary = []
for label, model, modal in variants:
    # --- relax pristine x = 1 -------------------------------------------------
    sc_full = lco_uc.copy(); sc_full.make_supercell([2, 2, 1])
    E_x1 = sevennet_relax(adaptor.get_atoms(sc_full), model, modal, f"x1_{label}")
    E_x1_per = E_x1 / n_co

    # --- relax bulk Li --------------------------------------------------------
    E_li = sevennet_relax(adaptor.get_atoms(li_bulk), model, modal, f"Li_{label}")
    E_li_atom = E_li / li_bulk.composition["Li"]

    # --- relax every x = 0.5 ordered derivative ------------------------------
    best_E05_per = None
    for i, st in enumerate(ordered_structs):
        tag = f"x0p5_{label}_{i}"
        E = sevennet_relax(adaptor.get_atoms(st), model, modal, tag)
        per_coo2 = E / n_co
        best_E05_per = per_coo2 if best_E05_per is None else min(best_E05_per, per_coo2)

    # --- average voltage ------------------------------------------------------
    V_half = (best_E05_per + 0.5 * E_li_atom - E_x1_per) / 0.5
    print("--------------------------------")
    print("V_half:", V_half)
    print("best_E05_per:", best_E05_per)
    print("E_li_atom:", E_li_atom)
    print("E_x1_per:", E_x1_per)
    print("--------------------------------")
    summary.append((label, V_half))

# ─── 3. print results ──────────────────────────────────────────────
print("\nAverage voltage for 0.5 < x < 1 (LiₓCoO₂)")
print("──────────────────────────────────────────")
for lbl, V in summary:
    print(f"{lbl:<25s}  {V: .3f} V")