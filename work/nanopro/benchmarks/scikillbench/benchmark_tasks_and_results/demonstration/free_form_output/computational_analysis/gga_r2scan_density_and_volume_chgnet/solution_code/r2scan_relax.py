import time
from pymatgen.core.structure import Structure
import torch
import json
import os
from chgnet.model import StructOptimizer
from chgnet.model.model import CHGNet

def load_icsd_structures(file_path="icsd_structure.json"):
    """Load ICSD structures from JSON file"""
    print(f"Loading ICSD structures from {file_path}...")
    with open(file_path, 'r') as file:
        data = json.load(file)
    
    structure_dicts = []
    structure_keys = []
    
    for key, structure_data in data.items():
        structure_dicts.append(structure_data)
        structure_keys.append(key)
    
    print(f"Loaded {len(structure_dicts)} structures")
    return structure_dicts, structure_keys

def main():
    start = time.time()

    # Load ICSD structures
    structure_dicts, structure_keys = load_icsd_structures()
    num_tasks = len(structure_dicts)
    
    print(f"Starting relaxation for {num_tasks} structures...")
    
    # Initialize the relaxer
    print("Initializing CHGNet model...")
    try:
        chgnet = CHGNet.load(model_name='r2scan')
        relaxer = StructOptimizer(model=chgnet, use_device='cuda')
        print("Model loaded successfully")
    except Exception as e:
        print(f"Failed to initialize model: {e}")
        return
    
    # Process structures
    print("Processing structures...")
    results_list = []
    for structure_dict, key in zip(structure_dicts, structure_keys):
        print(f"Processing {key}...")
        try:
            # Reconstruct structure from dict and store experimental properties
            struc = Structure.from_dict(structure_dict)
            num_atoms = len(struc)
            experimental_density = struc.density
            experimental_volume = struc.volume
            experimental_volume_per_atom = experimental_volume / num_atoms
            
            # Apply strain
            struc.apply_strain([-0.1, -0.1, -0.1])
            
            # Relax the structure with optimized parameters
            result = relaxer.relax(struc, steps=1000, fmax=0.03, verbose=False)
            
            # Get relaxed properties
            relaxed_structure = result['final_structure']
            relaxed_density = relaxed_structure.density
            relaxed_volume = relaxed_structure.volume
            relaxed_volume_per_atom = relaxed_volume / num_atoms
            
            # Calculate absolute errors
            density_absolute_error = abs(relaxed_density - experimental_density)
            volume_per_atom_absolute_error = abs(relaxed_volume_per_atom - experimental_volume_per_atom)
            
            result_data = {
                'icsd_key': key,
                'reduced formula': struc.composition.reduced_formula,
                'num_atoms': num_atoms,
                'experimental_density': experimental_density,
                'relaxed_density': relaxed_density,
                'density_absolute_error': density_absolute_error,
                'experimental_volume_per_atom': experimental_volume_per_atom,
                'relaxed_volume_per_atom': relaxed_volume_per_atom,
                'volume_per_atom_absolute_error': volume_per_atom_absolute_error
            }
            results_list.append(result_data)
            
        except Exception as e:
            print(f"Error processing {key}: {e}")
            error_result = {
                'icsd_key': key,
                'error': str(e)
            }
            results_list.append(error_result)
    
    # Filter results
    successful_results = [r for r in results_list if 'error' not in r]
    failed_results = [r for r in results_list if 'error' in r]
    
    # Summary
    total_time = time.time() - start
    print(f"\n=== Summary ===")
    print(f"Total time: {total_time:.2f}s")
    print(f"Successful: {len(successful_results)}/{num_tasks}")
    print(f"Failed: {len(failed_results)}")
    
    if successful_results:
        # Calculate average errors
        avg_density_error = sum([r['density_absolute_error'] for r in successful_results]) / len(successful_results)
        avg_volume_per_atom_error = sum([r['volume_per_atom_absolute_error'] for r in successful_results]) / len(successful_results)
        
        print(f"Average density error: {avg_density_error:.4f} g/cm³")
        print(f"Average volume per atom error: {avg_volume_per_atom_error:.4f} Å³/atom")
        
        # Save successful results
        output_file = 'icsd_relaxation_r2scan.json'
        with open(output_file, 'w') as f:
            json.dump(successful_results, f, indent=2)
        print(f"Saved results to {output_file}")
    
    if failed_results:
        # Save failed results
        failed_output_file = 'icsd_relaxation_failed_r2scan.json'
        with open(failed_output_file, 'w') as f:
            json.dump(failed_results, f, indent=2)
        print(f"Saved failed tasks to {failed_output_file}")
    
    # Cleanup
    print("Processing completed.")

if __name__ == "__main__":
    main()