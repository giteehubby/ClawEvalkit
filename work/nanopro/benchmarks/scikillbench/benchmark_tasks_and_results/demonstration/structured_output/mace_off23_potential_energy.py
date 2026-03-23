import requests
import tarfile
import tempfile
import os
from pathlib import Path
from ase.io import read, iread
from collections import Counter
from mace.calculators import mace_off

def download_mace_off23_dataset():
    """Download the MACE-OFF23 test dataset from Cambridge repository."""
    
    # URL for the test dataset (smaller file, 81.49 MB)
    url = "https://www.repository.cam.ac.uk/bitstreams/cb8351dd-f09c-413f-921c-67a702a7f0c5/download"
    
    print("Downloading MACE-OFF23 test dataset...")
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    tar_path = os.path.join(temp_dir, "test_large_neut_all.tar.gz")
    
    try:
        # Download the file
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(tar_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"Downloaded to: {tar_path}")
        
        # Extract the tar.gz file
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        
        with tarfile.open(tar_path, 'r:gz') as tar:
            # Use filter to avoid deprecation warning
            tar.extractall(extract_dir, filter='data')
        
        print(f"Extracted to: {extract_dir}")
        
        # Find the first .xyz file (exclude hidden files starting with ._)
        all_files = list(Path(extract_dir).rglob("*"))
        print(f"All extracted files: {[f.name for f in all_files]}")
        
        xyz_files = [f for f in Path(extract_dir).rglob("*.xyz") if not f.name.startswith('._')]
        if not xyz_files:
            raise FileNotFoundError("No .xyz files found in the extracted dataset")
        
        first_xyz = xyz_files[0]
        print(f"Found XYZ file: {first_xyz}")
        
        return first_xyz, temp_dir
        
    except Exception as e:
        # Clean up on error
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e

def calculate_energy_with_mace(xyz_file):
    """Calculate energy for the first structure using MACE-OFF calculator."""
    
    try:
        # Read all structures from the XYZ file
        structures = read(str(xyz_file), index=':')
        if not structures:
            raise ValueError("No structures found in the XYZ file")
        
        # Select the target unique formula's first occurrence
        target = "C19H22Cl2N4O2S"
        target_index = None
        print(f"Scanning for target formula: {target}")
        # Also count occurrences for confirmation
        try:
            count = 0
            indices = []
            for idx, frm in enumerate(iread(str(xyz_file), index=':', format='extxyz')):
                if frm.get_chemical_formula() == target:
                    count += 1
                    if len(indices) < 10:
                        indices.append(idx)
                    if target_index is None:
                        target_index = idx
            print(f"Occurrences of {target}: {count}")
            if indices:
                print(f"First indices (up to 10): {indices}")
        except Exception:
            print("Target formula scan skipped due to read error.")
        if target_index is None:
            raise ValueError(f"Target formula {target} not found in xyz")
        
        # Read only the target frame
        structure = read(str(xyz_file), index=target_index)
        print(f"Selected formula: {structure.get_chemical_formula()} @ index {target_index}")
        print(f"Number of atoms: {len(structure)}")
        # Set up MACE-OFF calculator
        calc = mace_off(model="small", device='cpu')  # Use CPU for compatibility
        structure.calc = calc
        
        # Calculate potential energy
        energy = structure.get_potential_energy()
        
        print(f"Potential energy: {energy:.6f} eV")
        
        return energy
        
    except Exception as e:
        print(f"Error calculating energy: {e}")
        raise

def main():
    """Main function to download dataset and calculate energy."""
    
    temp_dir = None
    
    try:
        # Download and extract dataset
        xyz_file, temp_dir = download_mace_off23_dataset()
        
        # Calculate energy for first structure
        energy = calculate_energy_with_mace(xyz_file)
        
        return energy
        
    except Exception as e:
        print(f"Error: {e}")
        return None
        
    finally:
        # Clean up temporary files
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("Cleaned up temporary files")

if __name__ == "__main__":
    result = main()
    if result is not None:
        print(f"\nFinal result: {result:.6f} eV")
