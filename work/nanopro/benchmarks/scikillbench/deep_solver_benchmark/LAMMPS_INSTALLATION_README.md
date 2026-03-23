# LAMMPS Installation Guide

## Installing LAMMPS

### 1. Download LAMMPS Source Code

```bash
# Create software directory
mkdir -p ~/software
cd ~/software

# Download latest stable release
wget https://download.lammps.org/tars/lammps-stable.tar.gz

# Extract the archive
tar -xvzf lammps-stable.tar.gz
cd lammps-*
```

### 2. Configure Build with Most Packages

```bash
# Create build directory
mkdir build
cd build

# Configure with most.cmake preset (includes comprehensive package support)
cmake ../cmake -C ../cmake/presets/most.cmake -DCMAKE_INSTALL_PREFIX=~/software/lammps/most
```

### 3. Build and Install

```bash
cmake --build . 

# Install to the specified prefix
cmake --install .
```

### 4. Set Up Environment

#### 4.1 Create Symbolic Link for Easy Access

```bash
# Create ~/bin directory if it doesn't exist
mkdir -p ~/bin

# Create symbolic link to LAMMPS executable
ln -sf ~/software/lammps/most/bin/lmp ~/bin/lmp

# Ensure ~/bin is in your PATH (add to ~/.bashrc if needed)
echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc
```

#### 4.2 Configure Potential File Environment Variable

```bash
# Set LAMMPS_POTENTIALS environment variable for automatic potential file discovery
echo 'export LAMMPS_POTENTIALS=$HOME/software/lammps/most/share/lammps/potentials' >> ~/.bashrc

# Reload bash configuration
source ~/.bashrc
```

### 5. Verify Installation

```bash
# Test LAMMPS installation
lmp -h

# Test potential file access (should not show errors)
echo "pair_style eam" | lmp -echo none -log none
```

### Potential File Not Found
If LAMMPS cannot find potential files:
1. Verify `LAMMPS_POTENTIALS` environment variable is set
2. Check that potential files exist in the specified directory
3. Alternatively, copy potential files to your working directory


## Installing LAMMPS Python Interface

To use LAMMPS directly from Python, you need to install the lammps Python module with shared library support.

### Step 1: Enable Shared Library Support

Edit the CMakeCache.txt file in your build directory:

```bash
# Navigate to your build directory
cd /path/to/lammps-source/build

# Edit CMakeCache.txt to enable shared libraries
# Change: BUILD_SHARED_LIBS:BOOL=OFF
# To:     BUILD_SHARED_LIBS:BOOL=ON
```

### Step 2: Rebuild LAMMPS with Shared Libraries

```bash
# Clean previous build
cmake --build . --target clean

# Reconfigure with shared library support
cmake .

# Build LAMMPS with shared libraries
cmake --build .
```

### Step 3: Install PyLAMMPS to Your Virtual Environment

**Important**: Make sure you're in your Python virtual environment before installation.

```bash
# Activate your virtual environment (example with conda/venv)
source /path/to/your/venv/bin/activate

# Install PyLAMMPS (this will detect your virtual environment automatically)
cmake --build . --target install-python
```

### Step 4: Test PyLAMMPS Installation

```python
# Test basic functionality
from lammps import lammps
lmp = lammps(cmdargs=['-screen', 'none'])
print(f"LAMMPS Version: {lmp.version()}")

# Test EAM potential (requires MANYBODY package)
lmp.command('units metal')
lmp.command('pair_style eam') 
print("✅ PyLAMMPS installation successful!")
lmp.close()
```

For more information, visit the official LAMMPS documentation: https://docs.lammps.org/

