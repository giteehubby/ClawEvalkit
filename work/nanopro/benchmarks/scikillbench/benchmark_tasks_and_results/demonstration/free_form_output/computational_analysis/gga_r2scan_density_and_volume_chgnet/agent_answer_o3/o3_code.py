# -------------------------------------------------------------
# Analyse systematic differences between CHGNet GGA vs R2SCAN
# -------------------------------------------------------------
import os, json, glob
from pathlib import Path
from typing import List, Tuple
import pandas as pd, numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from pymatgen.core import Structure
from chgnet.model.model import CHGNet
from chgnet.model import StructOptimizer

# -------------------------------------------------------------
# 0 – Locate dataset
# -------------------------------------------------------------
ICSD_PATH = Path(os.getenv("ICSD_DATA_PATH"))
if not ICSD_PATH.exists():
    raise FileNotFoundError("ICSD_DATA_PATH env-var missing / path invalid")
print(f"Dataset path detected: {ICSD_PATH}")

# -------------------------------------------------------------
# 1 – Load structures (folder with files OR single JSON bundle)
# -------------------------------------------------------------

def load_structures(target: Path) -> List[Tuple[str, Structure]]:
    structures = []
    if target.is_dir():
        for pat in ["*.cif", "*.json", "*.vasp", "POSCAR"]:
            for f in glob.glob(str(target/"**"/pat), recursive=True):
                try:
                    structures.append((f, Structure.from_file(f)))
                except Exception as e:
                    print(f"[WARN] skip {f}: {e}")
    else:  # assume JSON mapping id→structure-dict
        with open(target) as fh:
            data = json.load(fh)
        for key, sdict in data.items():
            try:
                structures.append((key, Structure.from_dict(sdict)))
            except Exception as e:
                print(f"[WARN] skip {key}: {e}")
    if not structures:
        raise RuntimeError("No structures loaded – check dataset")
    return structures

structures = load_structures(ICSD_PATH)
print(f"Total structures loaded: {len(structures)}")

# -------------------------------------------------------------
# 2 – Prepare CHGNet models & optimisers
# -------------------------------------------------------------
print("Initialising CHGNet models …")
model_gga    = CHGNet.load()              # default GGA/GGA+U
model_r2scan = CHGNet.load(model_name="r2scan")
relax_gga    = StructOptimizer(model_gga)
relax_r2     = StructOptimizer(model_r2scan)
FMAX = 0.03  # 30 meV/Å

# -------------------------------------------------------------
# 3 – Helpers
# -------------------------------------------------------------

def uniform_contract(s: Structure, factor: float = 0.99) -> Structure:
    new = s.copy(); new.scale_lattice(s.volume*(factor**3)); return new

def run_relax(relaxer: StructOptimizer, s: Structure) -> Structure:
    return relaxer.relax(s, fmax=FMAX, relax_cell=True)["final_structure"]

# -------------------------------------------------------------
# 4 – Main computation loop
# -------------------------------------------------------------
records, errors = [], []
for sid, exp_s in tqdm(structures, desc="Processing structures"):
    try:
        nat = len(exp_s)
        exp_v, exp_rho = exp_s.volume/nat, exp_s.density
        start = uniform_contract(exp_s)
        gga_s = run_relax(relax_gga, start)
        r2_s  = run_relax(relax_r2,  start)

        def m(s): return s.volume/len(s), s.density
        gga_v, gga_rho = m(gga_s)
        r2_v , r2_rho  = m(r2_s)
        records.append(dict(id=sid, formula=exp_s.composition.reduced_formula,
                            exp_Vpa=exp_v, exp_rho=exp_rho,
                            gga_Vpa=gga_v, gga_rho=gga_rho,
                            r2_Vpa=r2_v , r2_rho=r2_rho, natoms=nat))
    except Exception as e:
        errors.append((sid, str(e)))
        print(f"[ERROR] {sid}: {e}")

if not records:
    raise RuntimeError("All relaxations failed!")

# -------------------------------------------------------------
# 5 – DataFrame & statistics
# -------------------------------------------------------------
Df = pd.DataFrame(records)
for p, e, n in [("gga_Vpa","exp_Vpa","ΔVpa_gga"),("r2_Vpa","exp_Vpa","ΔVpa_r2"),
                ("gga_rho","exp_rho","Δrho_gga"),("r2_rho","exp_rho","Δrho_r2")]:
    Df[n] = Df[p]-Df[e]
print("\nSummary (mean ± std):")
for col in ["ΔVpa_gga","ΔVpa_r2","Δrho_gga","Δrho_r2"]:
    print(f"{col:>10}: {Df[col].mean(): .3f} ± {Df[col].std():.3f}")

# -------------------------------------------------------------
# 6 – Plots
# -------------------------------------------------------------
out = Path("chgnet_icsd_analysis_outputs"); out.mkdir(exist_ok=True)
sns.set_context("talk")
# scatter volume
plt.figure(figsize=(7,6))
plt.scatter(Df.exp_Vpa, Df.gga_Vpa,label="GGA/GGA+U",alpha=.7)
plt.scatter(Df.exp_Vpa, Df.r2_Vpa ,label="R2SCAN",   alpha=.7)
mx = Df[["exp_Vpa","gga_Vpa","r2_Vpa"]].to_numpy().max()
plt.plot([0,mx],[0,mx],'k--');plt.xlabel("Experimental V (Å³/atom)");plt.ylabel("Predicted V (Å³/atom)")
plt.legend();plt.tight_layout();plt.savefig(out/"scatter_volume_per_atom.png",dpi=300);plt.close()
# scatter rho
plt.figure(figsize=(7,6))
plt.scatter(Df.exp_rho, Df.gga_rho,label="GGA/GGA+U",alpha=.7)
plt.scatter(Df.exp_rho, Df.r2_rho ,label="R2SCAN",   alpha=.7)
mx = Df[["exp_rho","gga_rho","r2_rho"]].to_numpy().max()
plt.plot([0,mx],[0,mx],'k--');plt.xlabel("Experimental density (g/cm³)");plt.ylabel("Predicted density (g/cm³)")
plt.legend();plt.tight_layout();plt.savefig(out/"scatter_density.png",dpi=300);plt.close()
# histograms
plt.figure(figsize=(7,6))
sns.histplot(Df.ΔVpa_gga,kde=True,label="GGA/GGA+U",alpha=.6)
sns.histplot(Df.ΔVpa_r2 ,kde=True,label="R2SCAN"   ,alpha=.6)
plt.axvline(0,color='k',ls='--');plt.xlabel("Δ Volume/atom (Å³/atom)");plt.legend();plt.tight_layout();plt.savefig(out/"hist_delta_volume_per_atom.png",dpi=300);plt.close()
plt.figure(figsize=(7,6))
sns.histplot(Df.Δrho_gga,kde=True,label="GGA/GGA+U",alpha=.6)
sns.histplot(Df.Δrho_r2 ,kde=True,label="R2SCAN"   ,alpha=.6)
plt.axvline(0,color='k',ls='--');plt.xlabel("Δ Density (g/cm³)");plt.legend();plt.tight_layout();plt.savefig(out/"hist_delta_density.png",dpi=300);plt.close()
# save CSV
Df.to_csv(out/"relaxation_results.csv",index=False)
print(f"\nAll results saved to {out.resolve()}")
if errors:
    with open(out/"failed_structures.log","w") as fh:
        for sid,msg in errors: fh.write(f"{sid}: {msg}\n")
    print(f"Encountered {len(errors)} failures – see failed_structures.log")
print("Analysis complete.")