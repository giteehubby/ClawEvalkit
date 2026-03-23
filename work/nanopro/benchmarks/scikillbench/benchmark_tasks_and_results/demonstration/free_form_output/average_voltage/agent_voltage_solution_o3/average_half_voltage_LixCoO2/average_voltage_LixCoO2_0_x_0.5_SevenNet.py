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
from pymatgen.core import Species

warnings.filterwarnings("ignore")
API_KEY = os.getenv("MP_API_KEY")
adaptor = AseAtomsAdaptor()


# ─── helpers ────────────────────────────────────────────────────────
def fetch_structure(formula):
    with MPRester(API_KEY) as mpr:
        return mpr.materials.summary.search(
            formula=formula, energy_above_hull=(0, 0), fields=["structure"]
        )[0].structure


def sevennet_relax(atoms, model, modal, tag, steps=300, fmax=0.05):
    atoms = atoms.copy()
    atoms.calc = SevenNetCalculator(model=model, modal=modal, device="cpu")
    BFGS(UnitCellFilter(atoms), logfile=f"{tag}.log").run(fmax=fmax, steps=steps)
    return atoms.get_potential_energy()


# ─── 1. build super-cell & enumerate Li0.5 orderings once ───────────
lco_uc = fetch_structure("LiCoO2")
lco_uc.add_oxidation_state_by_guess()            # needed for Ewald

sup = lco_uc.copy()
sup.make_supercell([2, 2, 1])                    # Li4Co4O8 (4 CoO₂ units)
n_co = sup.composition["Co"]                     # 4 formula units

for site in sup:
    if site.specie.symbol == "Li":
        site.species = {site.specie: 0.5}

odt = OrderDisorderedStructureTransformation()
ordered_structs = [
    d["structure"] for d in odt.apply_transformation(sup, return_ranked_list=5)
]

li_bulk = fetch_structure("Li")

# ─── 2. model list ──────────────────────────────────────────────────
variants = [
    ("MF-ompa  MPtrj+sAlex", "7net-mf-ompa", "mpa"),
    ("MF-ompa  OMat24",      "7net-mf-ompa", "omat24"),
    ("MF-0     PBE+U",       "7net-mf-0",    "PBE"),
    ("MF-0     r²SCAN",      "7net-mf-0",    "R2SCAN"),
]

print("Will evaluate", len(ordered_structs), "ordered Li0.5 structures per model")

summary = []
for label, model, modal in variants:
    # ----- relax all x = 0.5 orderings and pick best ----------------
    best_E05_per = None
    for i, st in enumerate(ordered_structs):
        Etot = sevennet_relax(adaptor.get_atoms(st), model, modal,
                              tag=f"x0p5_{label}_{i}")
        per = Etot / n_co
        best_E05_per = per if best_E05_per is None else min(best_E05_per, per)

   # --- fully delithiated CoO2 (same super-cell size) -----------------
    sc_coo2 = lco_uc.copy()            # start from ordered unit cell
    sc_coo2.make_supercell([2, 2, 1])  # same shape as x = 1 and x = 0.5
    Li_plus = Species("Li", 1) 
    print(Li_plus)
    sc_coo2.remove_species([Li_plus])     # now perfectly ordered CoO2
    E_coo2_per = (
        sevennet_relax(adaptor.get_atoms(sc_coo2), model, modal, f"CoO2_{label}")
        / n_co
    )

    # ----- Li metal reference ---------------------------------------
    E_li_atom = sevennet_relax(adaptor.get_atoms(li_bulk), model, modal,
                               tag=f"Li_{label}") / li_bulk.composition["Li"]

    # ----- voltage for 0 < x < 0.5 ----------------------------------
    V_low = (E_coo2_per + 0.5 * E_li_atom - best_E05_per) / 0.5
    print("--------------------------------")
    print("V_low:", V_low)
    print("E_coo2_per:", E_coo2_per)
    print("E_li_atom:", E_li_atom)
    print("best_E05_per:", best_E05_per)
    print("--------------------------------")
    summary.append((label, V_low))

# ─── 3. report ──────────────────────────────────────────────────────
print("\nAverage voltage for 0 < x < 0.5 (LiₓCoO₂)")
print("──────────────────────────────────────────")
for lbl, V in summary:
    print(f"{lbl:<25s}  {V: .3f} V")