# Large Files Fix Guide

## Problem

The ClawEvalKit repository is currently **883 MB**, which makes `git clone` extremely slow
(5–10 min) and blocks external contributors. Root causes:

| Issue | Size | Location |
|-------|------|----------|
| Benchmark data committed directly to git | ~891 MB | `benchmarks/` |
| Python wheels committed to git | ~40 MB | `assets/wheels/` |
| SkillsBench data stored 3× (`tasks/`, `tasks-no-skills/`, `tasks_no_skills_generate/`) | ~132 MB redundant | `benchmarks/skillsbench/` |

---

## Step 1: Enable Git LFS (maintainer action)

This PR adds `.gitattributes` rules. To migrate **existing** history:

```bash
# Install git-lfs (once per machine)
git lfs install

# Migrate existing large files to LFS (rewrites history!)
git lfs migrate import \
  --include="*.csv,*.whl,*.mp4,*.pcap,*.pptx,benchmarks/**/*.pdf,benchmarks/**/*.png,benchmarks/**/*.json" \
  --everything

# Force-push all branches (all contributors must re-clone after this)
git push --force --all
git push --force --tags
```

> ⚠️ History rewrite requires coordination with all contributors.

---

## Step 2: Remove `assets/wheels/` from history

```bash
# Remove wheel files from git history
pip install git-filter-repo
git filter-repo --path assets/wheels/ --invert-paths

git push --force --all
```

After this, wheels can be installed via `pip install -r requirements.txt`.

---

## Step 3: Eliminate duplicate SkillsBench data

The three task variants share identical large files (e.g. `citsci_train.csv` 44 MB × 3 = 132 MB).

**Recommended fix:** Generate `tasks-no-skills/` and `tasks_no_skills_generate/` at runtime
from the canonical `tasks/` directory instead of storing static copies.

---

## Step 4 (Long-term): Move benchmark data to HuggingFace

```python
# Example: upload benchmarks to HF Hub
from huggingface_hub import HfApi
api = HfApi()
api.upload_folder(folder_path="benchmarks/", repo_id="your-org/clawevalkit-benchmarks", repo_type="dataset")
```

Then add a `benchmarks/download.py` script that fetches data on first run.

---

## Estimated Impact

| Metric | Before | After full migration |
|--------|--------|----------------------|
| Repository size | 883 MB | ~30–50 MB |
| `git clone` time | 5–10 min | < 30 sec |
| CI/CD time | slow | fast |

