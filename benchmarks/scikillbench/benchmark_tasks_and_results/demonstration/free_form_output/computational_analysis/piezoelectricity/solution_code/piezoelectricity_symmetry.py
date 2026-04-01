from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
import json
import warnings
warnings.filterwarnings("ignore", module="pymatgen")

structure = Structure.from_dict(json.load(open("structure.json")))

sga = SpacegroupAnalyzer(structure)

# Use is_laue() method to determine if centrosymmetric
# is_laue() == True means centrosymmetric (no piezoelectricity)
is_centrosymmetric = sga.is_laue()
is_piezoelectric = not is_centrosymmetric

print(f"Space group: {sga.get_space_group_symbol()}")
print(f"Point group: {sga.get_point_group_symbol()}")
print(f"Is centrosymmetric: {is_centrosymmetric}")
print(f"Is piezoelectric: {is_piezoelectric}")