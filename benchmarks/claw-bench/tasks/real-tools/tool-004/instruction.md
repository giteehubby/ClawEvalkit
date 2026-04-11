# Task: Build Script (Makefile)

You are given a JSON file describing a Python project structure. Generate a comprehensive Makefile.

## Input Files

- `workspace/project_structure.json` — JSON describing the project layout, source files, test files, documentation, and dependencies

## Goal

Create a well-structured `Makefile` with standard development targets for the Python project.

## Requirements

1. Read `workspace/project_structure.json` for project context.
2. Create `workspace/Makefile` with the following targets:

### Required Targets

| Target    | Purpose                                        |
|-----------|------------------------------------------------|
| `install` | Install dependencies from requirements.txt     |
| `test`    | Run tests using pytest                         |
| `lint`    | Run linting (flake8, pylint, or ruff)          |
| `build`   | Build the project (e.g., python -m build)      |
| `clean`   | Remove build artifacts, caches, __pycache__    |
| `docs`    | Generate documentation (e.g., using mkdocs/sphinx) |
| `all`     | Meta-target depending on install, test, and lint |

3. Makefile formatting:
   - Use **tabs** (not spaces) for recipe indentation — this is mandatory for Make
   - Include a `.PHONY` declaration for all targets
   - Include helpful comments for each target
   - Targets should have logical dependencies (e.g., `test` depends on `install`)

## Notes

- The Makefile should be production-quality and follow best practices.
- Use standard Python tooling (pip, pytest, flake8/ruff, etc.).
- The `clean` target should remove common Python artifacts: `__pycache__`, `.pytest_cache`, `dist/`, `build/`, `*.egg-info`.
