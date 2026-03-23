## Free-form Demonstrations

This directory contains examples where the final answer can be free-form (explanations, plots, text), not constrained to a strict output schema.

### When to use
- You will manually assess the result and explanation.
- You do not need strict formatting for automated accuracy scoring.

### Agent variant for free-form output
Replace files in `deep_solver_benchmark/deep_solver/` with those from `deep_solver_benchmark/deep_solver_free_form/`:

```bash
cd CASCADE/deep_solver_benchmark

# Backup original files first
mkdir -p deep_solver_backup
cp deep_solver/*.py deep_solver_backup/

# Replace with free-form variant
cp deep_solver_free_form/*.py deep_solver/
```

This produces human-readable explanations instead of structured Pydantic output.

To restore original files:
```bash
cp deep_solver_backup/*.py deep_solver/
```

### Run in single-query mode
From `CASCADE/deep_solver_benchmark/`:
```bash
python -u test_workflow.py
```
- Use this single-query mode and paste the user_query from the JSON in this folder. Or you can ask your own questions.
- Review the agent's output, which will include explanations/analysis tailored to the query.

### Environment variables used by examples
- `STRUCTURE_PATH`: path to structure.json in deep_solver_benchmark/data_for_demonstration/.
- `ICSD_DATA_PATH`: path to icsd_structure.json in deep_solver_benchmark/data_for_demonstration/.
- `PEIS_DATA_PATH`: path to Li2Fe0p8Ni0p2Cl4_PEIS.json in deep_solver_benchmark/data_for_demonstration/.

Set them in your shell startup (e.g., `~/.bashrc`) with `export NAME=/abs/path` and reload the shell.

Example (replace with your absolute paths):
```bash
export STRUCTURE_PATH="/your/absolute/path/CASCADE/deep_solver_benchmark/data_for_demonstration/structure.json"
export ICSD_DATA_PATH="/your/absolute/path/CASCADE/deep_solver_benchmark/data_for_demonstration/icsd_structure.json"
export PEIS_DATA_PATH="/your/absolute/path/CASCADE/deep_solver_benchmark/data_for_demonstration/Li2Fe0p8Ni0p2Cl4_PEIS.json"
source ~/.bashrc  # or open a new shell
```

Quick check:
```bash
echo $STRUCTURE_PATH; echo $ICSD_DATA_PATH; echo $PEIS_DATA_PATH
```
