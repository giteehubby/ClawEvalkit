# Dockerfile for Claude Code baseline evaluation with xtb
FROM python:3.12-slim

# Set working directory (not used by agent, but required by Dockerfile)
WORKDIR /tmp

# Install system dependencies and Node.js (required for Claude Code)
# Also install X11 libraries for Open Babel, procps for ps command, gfortran for enumlib, and OpenBLAS for LAMMPS
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    ca-certificates \
    gnupg \
    procps \
    libxrender1 \
    libxext6 \
    libsm6 \
    libice6 \
    gfortran \
    libgfortran5 \
    libopenblas0 \
    libopenmpi40 \
    libhwloc-dev \
    libevent-dev \
    zlib1g \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager
RUN pip install uv

# Copy and install Python packages
# Using the requirements.txt from the main project
COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --system -r /tmp/requirements.txt

# Install Claude Agent SDK
RUN uv pip install --system claude-agent-sdk

# Install LAMMPS Python module from pre-built wheel
# This provides LAMMPS molecular dynamics simulation capabilities
COPY lammps-2025.7.22-cp312-cp312-linux_x86_64.whl /tmp/lammps-2025.7.22-cp312-cp312-linux_x86_64.whl
RUN uv pip install --system /tmp/lammps-2025.7.22-cp312-cp312-linux_x86_64.whl && rm /tmp/lammps-2025.7.22-cp312-cp312-linux_x86_64.whl

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy xtb binary from host (statically linked, no dependencies needed)
# This adds the xtb computational chemistry software to the container
COPY xtb /usr/local/bin/xtb
RUN chmod +x /usr/local/bin/xtb

# Copy ORCA directory from host (includes main executable and all auxiliary programs)
# ORCA is a quantum chemistry software package for molecular and periodic calculations
COPY orca_6_1_0 /opt/orca
RUN chmod +x /opt/orca/orca && \
    chmod +x /opt/orca/orca_* && \
    chmod +x /opt/orca/autoci_* && \
    ln -s /opt/orca/orca /usr/local/bin/orca

# Copy enumlib executables from host (required for pymatgen EnumerateStructureTransformation)
# These executables are used for structure enumeration in materials science
COPY enum.x /usr/local/bin/enum.x
COPY makeStr.py /usr/local/bin/makeStr.py
RUN chmod +x /usr/local/bin/enum.x /usr/local/bin/makeStr.py

# Copy LAMMPS executable and potential files
# lmp: LAMMPS command-line executable for running input scripts
COPY lmp /usr/local/bin/lmp
RUN chmod +x /usr/local/bin/lmp

# Copy LAMMPS potential files directory
# This contains 257 potential files for various materials (EAM, MEAM, ADP, etc.)
COPY lammps_potentials /usr/local/share/lammps/potentials
ENV LAMMPS_POTENTIALS=/usr/local/share/lammps/potentials

# Copy runner script to system path (not visible in agent workspace)
# This ensures agent cannot see or modify the runner script
COPY claude_code_runner.py /usr/local/bin/claude_code_runner.py
RUN chmod +x /usr/local/bin/claude_code_runner.py

# Create user (no need for workspace directories since agent uses /tmp)
RUN useradd -m -u 1000 claude_user

# Set environment variables
ENV MP_API_KEY=""
ENV ANTHROPIC_API_KEY=""
ENV PATH="/opt/orca:/usr/local/lib/node_modules/.bin:${PATH}"

USER claude_user

# Default command shows help
CMD ["python", "claude_code_runner.py", "--help"]
