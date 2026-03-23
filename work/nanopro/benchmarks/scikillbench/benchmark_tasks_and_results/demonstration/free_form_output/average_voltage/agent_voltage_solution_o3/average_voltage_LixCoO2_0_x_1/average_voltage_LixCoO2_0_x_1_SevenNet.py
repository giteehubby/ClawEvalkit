import os
from mp_api.client import MPRester
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.core.composition import Composition
from ase.filters import UnitCellFilter
from ase.optimize import BFGS
from sevenn.calculator import SevenNetCalculator

API_KEY = os.getenv("MP_API_KEY")          # ← your Materials Project key
if not API_KEY:
    raise RuntimeError("export MP_API_KEY first")

adaptor = AseAtomsAdaptor()

# ---------------------------------------------------------------------------
# helper functions
# ---------------------------------------------------------------------------
def fetch_ground_state(formula):
    with MPRester(API_KEY) as mpr:
        return mpr.materials.summary.search(
            formula=formula,
            energy_above_hull=(0, 0),
            fields=["structure", "material_id"],
        )[0]


def relax(atoms, model, modal, fmax=0.05, steps=300):
    atoms.calc = SevenNetCalculator(model=model, modal=modal, device="cpu")
    BFGS(UnitCellFilter(atoms), logfile=None).run(fmax=fmax, steps=steps)
    return atoms.get_potential_energy()


def efu(structure, e_tot):
    _, n = Composition(structure.composition).get_reduced_formula_and_factor()
    return e_tot / n


# ---------------------------------------------------------------------------
# ground-state structures fetched once
# ---------------------------------------------------------------------------
lco_doc = fetch_ground_state("LiCoO2")
li_doc  = fetch_ground_state("Li")
lco_init = lco_doc.structure
li_init  = li_doc.structure

# ---------------------------------------------------------------------------
# SevenNet variants to test
# ---------------------------------------------------------------------------
variants = [
    ("MF-ompa  (MPtrj+sAlex)", "7net-mf-ompa", "mpa"),
    ("MF-ompa  (OMat24 only)", "7net-mf-ompa", "omat24"),
    ("MF-0     (PBE+U)",       "7net-MF-0",    "PBE"),
    ("MF-0     (r²SCAN)",       "7net-MF-0",    "R2SCAN"),
]

results = []
for label, model, modal in variants:
    print(f"\n=== {label} ===")
    # 1) LiCoO2
    lco_atoms = adaptor.get_atoms(lco_init)
    E_LCO  = relax(lco_atoms, model, modal)
    lco_rel = adaptor.get_structure(lco_atoms)
    Efu_LCO = efu(lco_rel, E_LCO)

    # 2) CoO2 made with pymatgen (Li removed), then relaxed
    coo2_seed = lco_rel.copy()
    coo2_seed.remove_species(["Li"])
    coo2_atoms = adaptor.get_atoms(coo2_seed)
    E_COO2  = relax(coo2_atoms, model, modal)
    coo2_rel = adaptor.get_structure(coo2_atoms)
    Efu_COO2 = efu(coo2_rel, E_COO2)

    # 3) Li metal
    li_atoms = adaptor.get_atoms(li_init)
    E_Li   = relax(li_atoms, model, modal)
    Efu_Li = efu(li_init, E_Li)      # per reduced formula unit (=per atom)

    # 4) Voltage
    V = Efu_Li + Efu_COO2 - Efu_LCO
    print(f"Voltage  = {V:.3f}  V")

    results.append(
        (label, V, Efu_LCO, Efu_COO2, Efu_Li)
    )

# ---------------------------------------------------------------------------
# tidy summary
# ---------------------------------------------------------------------------
print("\n=====  SUMMARY  (energies in eV per r.f.u.) =====")
for lbl, V, e_lco, e_coo2, e_li in results:
    print(f"{lbl:<26}  V = {V: .3f}   "
          f"E_LCO = {e_lco: .3f}   E_COO2 = {e_coo2: .3f}   E_Li = {e_li: .3f}")