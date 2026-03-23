#!/usr/bin/env python3
"""
Plot density ratio and volume per atom ratio distributions comparing R2SCAN and GGA relaxation results
"""

import json
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
from typing import Dict, List, Optional

# Global style
sns.set(style="ticks")
sns.set_context("talk")
plt.rc('font', family='DejaVu Sans', size=16)
l_w = 2  # line width
s = 50
alpha = 0.07

# Colors: red for R2SCAN, green for GGA
method_colors = {
    'R2SCAN': '#ff4444',
    'GGA': '#44aa44'
}

def load_and_process_data():
    """Load both R2SCAN and GGA relaxation data and extract density and volume per atom data"""
    data_dict = {}
    
    # Load R2SCAN data
    r2scan_filename = 'icsd_relaxation_r2scan.json'
    print(f"Loading R2SCAN data from {r2scan_filename}...")
    
    try:
        with open(r2scan_filename, 'r') as f:
            r2scan_data = json.load(f)
        
        # Extract R2SCAN data
        exp_densities_r2scan = []
        pred_densities_r2scan = []
        exp_volumes_per_atom_r2scan = []
        pred_volumes_per_atom_r2scan = []
        
        for entry in r2scan_data:
            if isinstance(entry, dict):
                # Density data
                if 'experimental_density' in entry and 'relaxed_density' in entry:
                    exp_density = entry['experimental_density']
                    pred_density = entry['relaxed_density']
                    
                    if exp_density is not None and pred_density is not None:
                        if isinstance(exp_density, (int, float)) and isinstance(pred_density, (int, float)):
                            exp_densities_r2scan.append(exp_density)
                            pred_densities_r2scan.append(pred_density)
                
                # Volume per atom data
                if 'experimental_volume_per_atom' in entry and 'relaxed_volume_per_atom' in entry:
                    exp_vpa = entry['experimental_volume_per_atom']
                    pred_vpa = entry['relaxed_volume_per_atom']
                    
                    if exp_vpa is not None and pred_vpa is not None:
                        if isinstance(exp_vpa, (int, float)) and isinstance(pred_vpa, (int, float)):
                            exp_volumes_per_atom_r2scan.append(exp_vpa)
                            pred_volumes_per_atom_r2scan.append(pred_vpa)
        
        if len(exp_densities_r2scan) > 0:
            data_dict['R2SCAN'] = {
                'exp_densities': np.array(exp_densities_r2scan),
                'pred_densities': np.array(pred_densities_r2scan),
                'exp_volumes_per_atom': np.array(exp_volumes_per_atom_r2scan),
                'pred_volumes_per_atom': np.array(pred_volumes_per_atom_r2scan)
            }
            print(f"Loaded R2SCAN: {len(exp_densities_r2scan)} density entries, {len(exp_volumes_per_atom_r2scan)} volume per atom entries")
        
    except Exception as e:
        print(f"Error loading R2SCAN data: {e}")
    
    # Load GGA data
    gga_filename = 'icsd_relaxation_gga.json'
    print(f"Loading GGA data from {gga_filename}...")
    
    try:
        with open(gga_filename, 'r') as f:
            gga_data = json.load(f)
        
        # Extract GGA data
        exp_densities_gga = []
        pred_densities_gga = []
        exp_volumes_per_atom_gga = []
        pred_volumes_per_atom_gga = []
        
        for entry in gga_data:
            if isinstance(entry, dict):
                # Density data
                if 'experimental_density' in entry and 'relaxed_density' in entry:
                    exp_density = entry['experimental_density']
                    pred_density = entry['relaxed_density']
                    
                    if exp_density is not None and pred_density is not None:
                        if isinstance(exp_density, (int, float)) and isinstance(pred_density, (int, float)):
                            exp_densities_gga.append(exp_density)
                            pred_densities_gga.append(pred_density)
                
                # Volume per atom data
                if 'experimental_volume_per_atom' in entry and 'relaxed_volume_per_atom' in entry:
                    exp_vpa = entry['experimental_volume_per_atom']
                    pred_vpa = entry['relaxed_volume_per_atom']
                    
                    if exp_vpa is not None and pred_vpa is not None:
                        if isinstance(exp_vpa, (int, float)) and isinstance(pred_vpa, (int, float)):
                            exp_volumes_per_atom_gga.append(exp_vpa)
                            pred_volumes_per_atom_gga.append(pred_vpa)
        
        if len(exp_densities_gga) > 0:
            data_dict['GGA'] = {
                'exp_densities': np.array(exp_densities_gga),
                'pred_densities': np.array(pred_densities_gga),
                'exp_volumes_per_atom': np.array(exp_volumes_per_atom_gga),
                'pred_volumes_per_atom': np.array(pred_volumes_per_atom_gga)
            }
            print(f"Loaded GGA: {len(exp_densities_gga)} density entries, {len(exp_volumes_per_atom_gga)} volume per atom entries")
        
    except Exception as e:
        print(f"Error loading GGA data: {e}")
    
    return data_dict

def plot_density_ratio_distribution(data_dict):
    """Create density ratio distribution plot comparing R2SCAN and GGA"""
    
    # Set up the plot style
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Plot ratio for both methods
    for method_name, data in data_dict.items():
        if len(data['exp_densities']) > 0:
            exp_densities = data['exp_densities']
            pred_densities = data['pred_densities']
            
            # Calculate ratio: exp / predicted
            ratio = np.where(pred_densities != 0, exp_densities / pred_densities, np.nan)
            ratio = ratio[~np.isnan(ratio)]  # Remove NaN values
            
            if len(ratio) > 0:
                # Use specific colors for each method
                color = method_colors[method_name]
                
                # Plot histogram with consistent styling
                ax.hist(ratio, bins=41, range=(0.8, 1.2), density=False, 
                       color=color, alpha=0.3, label=method_name)
                
                # Also plot as line for better visibility
                hist, bins = np.histogram(ratio, bins=41, range=(0.8, 1.2), density=False)
                bin_centers = (bins[:-1] + bins[1:]) / 2
                ax.plot(bin_centers, hist, color=color, 
                       linewidth=l_w * 1.5, alpha=0.9)
    
    # Add a vertical line at ratio = 1 (perfect prediction)
    ax.axvline(x=1.0, color='k', linestyle='--', linewidth=l_w, 
              label='Perfect Prediction (Ratio = 1)', alpha=0.5)
    
    # Customize the plot
    ax.set_xlabel('Density Ratio (Experimental / Predicted)', fontsize=14, fontweight='normal')
    ax.set_ylabel('Count', fontsize=14, fontweight='normal')
    
    # Clean legend styling
    ax.legend(loc='upper right', frameon=True, fontsize=12, framealpha=1.0, 
              edgecolor='black', fancybox=False)
    
    # Set axis limits
    ax.set_xlim(0.8, 1.2)
    
    # Clean tick styling
    ax.tick_params(axis='both', which='major', labelsize=12)
    
    # Tight layout
    plt.tight_layout()
    
    return fig

def plot_volume_per_atom_ratio_distribution(data_dict):
    """Create volume per atom ratio distribution plot comparing R2SCAN and GGA"""
    
    # Set up the plot style
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Plot ratio for both methods
    for method_name, data in data_dict.items():
        if len(data['exp_volumes_per_atom']) > 0:
            exp_volumes = data['exp_volumes_per_atom']
            pred_volumes = data['pred_volumes_per_atom']
            
            # Calculate ratio: exp / predicted
            ratio = np.where(pred_volumes != 0, exp_volumes / pred_volumes, np.nan)
            ratio = ratio[~np.isnan(ratio)]  # Remove NaN values
            
            if len(ratio) > 0:
                # Use specific colors for each method
                color = method_colors[method_name]
                
                # Plot histogram with consistent styling
                ax.hist(ratio, bins=41, range=(0.8, 1.2), density=False, 
                       color=color, alpha=0.3, label=method_name)
                
                # Also plot as line for better visibility
                hist, bins = np.histogram(ratio, bins=41, range=(0.8, 1.2), density=False)
                bin_centers = (bins[:-1] + bins[1:]) / 2
                ax.plot(bin_centers, hist, color=color, 
                       linewidth=l_w * 1.5, alpha=0.9)
    
    # Add a vertical line at ratio = 1 (perfect prediction)
    ax.axvline(x=1.0, color='k', linestyle='--', linewidth=l_w, 
              label='Perfect Prediction (Ratio = 1)', alpha=0.5)
    
    # Customize the plot
    ax.set_xlabel('Volume per Atom Ratio (Experimental / Predicted)', fontsize=14, fontweight='normal')
    ax.set_ylabel('Count', fontsize=14, fontweight='normal')
    
    # Clean legend styling
    ax.legend(loc='upper right', frameon=True, fontsize=12, framealpha=1.0, 
              edgecolor='black', fancybox=False)
    
    # Set axis limits
    ax.set_xlim(0.8, 1.2)
    
    # Clean tick styling
    ax.tick_params(axis='both', which='major', labelsize=12)
    
    # Tight layout
    plt.tight_layout()
    
    return fig

def main():
    """Main function to create and save ratio comparison plots"""
    print("Loading data from R2SCAN and GGA relaxation results...")
    
    # Load data
    data_dict = load_and_process_data()
    
    if not data_dict:
        print("No data found! Please check if the JSON files exist.")
        return
    
    print(f"Loaded data for {len(data_dict)} methods:")
    for label, data in data_dict.items():
        print(f"  {label}: {len(data['exp_densities'])} density points, {len(data['exp_volumes_per_atom'])} volume per atom points")
    
    # Create density ratio plot
    print("Creating density ratio distribution plot...")
    fig_density = plot_density_ratio_distribution(data_dict)
    
    # Save the density plot as PNG
    density_filename = "density_ratio_distribution_comparison.png"
    fig_density.savefig(density_filename, dpi=300, bbox_inches='tight', format='png')
    print(f"Saved {density_filename}")
    plt.close(fig_density)
    
    # Create volume per atom ratio plot
    print("Creating volume per atom ratio distribution plot...")
    fig_volume = plot_volume_per_atom_ratio_distribution(data_dict)
    
    # Save the volume plot as PNG
    volume_filename = "volume_per_atom_ratio_distribution_comparison.png"
    fig_volume.savefig(volume_filename, dpi=300, bbox_inches='tight', format='png')
    print(f"Saved {volume_filename}")
    plt.close(fig_volume)
    
    print("\nBoth ratio distribution plots created successfully!")

if __name__ == "__main__":
    main() 