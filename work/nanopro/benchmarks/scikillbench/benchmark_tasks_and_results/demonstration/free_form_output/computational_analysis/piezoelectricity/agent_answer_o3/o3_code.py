import os
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

# Read structure path from environment variable
structure_path = os.getenv("STRUCTURE_PATH")
if structure_path is None:
    raise EnvironmentError("STRUCTURE_PATH environment variable not set.")

# Load the structure using pymatgen
structure = Structure.from_file(structure_path)

# Analyze symmetry
sga = SpacegroupAnalyzer(structure, symprec=1e-2)  # default tolerances

# Criterion for piezoelectricity:
# 1) Structure must be non-centrosymmetric (i.e., not a Laue group)
# 2) Point group must not be 432 (non-piezoelectric although non-centrosymmetric)
non_centrosymmetric = not sga.is_laue()
point_group = sga.get_point_group_symbol()  # e.g. "4mm", "m", "432", etc.

has_piezoelectricity = non_centrosymmetric and point_group != "432"

print(f"Structure path: {structure_path}")
print(f"Space group symbol: {sga.get_space_group_symbol()} (number {sga.get_space_group_number()})")
print(f"Point group: {point_group}")
print(f"Centrosymmetric: {not non_centrosymmetric}")
print("Piezoelectric: {}".format("Yes" if has_piezoelectricity else "No"))