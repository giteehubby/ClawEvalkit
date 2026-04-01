#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

# Use printf with explicit tabs to guarantee correct Makefile formatting
cat > "$WORKSPACE/Makefile" << 'MAKEFILE'
.PHONY: all install test lint build clean docs help

# Default target
all: install test lint

# Install project dependencies
install:
	pip install -r requirements.txt

# Run test suite with pytest
test: install
	python -m pytest tests/ -v --tb=short

# Run linting checks
lint:
	python -m flake8 src/ tests/
	python -m black --check src/ tests/

# Build the project package
build: clean
	python -m build

# Remove build artifacts and caches
clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Generate documentation
docs:
	mkdocs build

# Show available targets
help:
	@echo "Available targets:"
	@echo "  install  - Install dependencies from requirements.txt"
	@echo "  test     - Run tests with pytest"
	@echo "  lint     - Run flake8 and black checks"
	@echo "  build    - Build the project package"
	@echo "  clean    - Remove build artifacts and caches"
	@echo "  docs     - Generate documentation with mkdocs"
	@echo "  all      - Run install, test, and lint"
	@echo "  help     - Show this help message"
MAKEFILE

echo "Created Makefile in $WORKSPACE"
