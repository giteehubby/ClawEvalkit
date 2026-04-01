---
id: 01_Productivity_Flow_task_2_table_tex_download
name: Recover Original Table TeX from arXiv Source
category: 01_Productivity_Flow
timeout_seconds: 900
---

## Prompt

I want to recover original LaTeX table source from an arXiv paper.

Please work on this paper:

- Paper URL: `https://arxiv.org/abs/2501.07888`

Your task is to find the corresponding original arXiv source package, download it, and extract **all table environments from the paper source**. You should delete the source package after extracting.

Save the results into `/tmp_workspace/results`.

- Save each recovered table as a separate file named `1.tex`, `2.tex`, `3.tex`, ...
- Number the files in the order the tables appear in the paper
- Each file must contain exactly one original LaTeX `table` environment copied from the source package
- Preserve the original table content and formatting as much as possible
- Do not merge multiple tables into one file
- Do not wrap the table with extra explanation, markdown, or prose
- Do not skip numbers in the sequence
- Only generate the required output files

## Expected Behavior

The agent should:

1. Resolve the paper URL to the corresponding arXiv source package
2. Download the original source archive
3. Identify every table environment belonging to the paper
4. Save each table as a separate numbered `.tex` file in the correct order
5. Save only the numbered `.tex` files needed for grading

The agent may use web access, archive download, shell commands, or scripts, but the final score is based on whether the downloaded table sources match the original source tables.

## Grading Criteria

- [ ] The numbered `.tex` files are created with the required naming convention
- [ ] `n.tex` exactly matches the n-th ground-truth table after normalization
- [ ] Strict ordered match ratio is high
- [ ] Unordered exact-match recall is high
- [ ] Unordered exact-match precision is high
- [ ] Unordered exact-match F1 is high

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the table-tex extraction task.

    Args:

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    from pathlib import Path
    import re

    workspace = Path("/tmp_workspace/results")
    gt_dir = Path("/tmp_workspace") / "gt"

    def normalize_tex(text: str) -> str:
        text = text.strip()
        text = re.sub(r"%[^\n]*", "", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text

    if not gt_dir.exists() or not gt_dir.is_dir():
        return {"error": f"gt_dir does not exist or is not a directory: {gt_dir}"}

    gt_files = sorted(gt_dir.glob("*.tex"), key=lambda p: int(p.stem))
    gt_contents = [normalize_tex(f.read_text(encoding="utf-8")) for f in gt_files]
    num_gt = len(gt_contents)

    if num_gt == 0:
        return {"error": f"no .tex files found under gt_dir: {gt_dir}"}

    ALL_CRITERIA = (
        ["files_created"]
        + [f"ordered_match_{i}" for i in range(1, num_gt + 1)]
        + ["strict_ordered_ratio", "unordered_recall", "unordered_precision", "unordered_f1", "overall_score"]
    )

    if not workspace.exists() or not workspace.is_dir():
        return {k: 0.0 for k in ALL_CRITERIA} | {"error": f"workspace not found: {workspace}"}

    pred_files = sorted(
        [p for p in workspace.glob("*.tex") if p.stem.isdigit()],
        key=lambda p: int(p.stem),
    )
    pred_contents = [normalize_tex(f.read_text(encoding="utf-8")) for f in pred_files]
    num_pred = len(pred_contents)
    scores = {}

    scores["files_created"] = 1.0 if num_pred > 0 else 0.0

    for i in range(1, num_gt + 1):
        key = f"ordered_match_{i}"
        if i - 1 < num_pred and i - 1 < num_gt:
            scores[key] = 1.0 if pred_contents[i - 1] == gt_contents[i - 1] else 0.0
        else:
            scores[key] = 0.0

    ordered_correct = 0
    for i in range(min(num_pred, num_gt)):
        if pred_contents[i] == gt_contents[i]:
            ordered_correct += 1
    scores["strict_ordered_ratio"] = round(ordered_correct / num_gt, 4)

    gt_matched = set()
    pred_matched = set()
    for pi, pc in enumerate(pred_contents):
        for gi, gc in enumerate(gt_contents):
            if gi not in gt_matched and pc == gc:
                gt_matched.add(gi)
                pred_matched.add(pi)
                break

    recall = len(gt_matched) / num_gt if num_gt > 0 else 0.0
    precision = len(pred_matched) / num_pred if num_pred > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    scores["unordered_recall"] = round(recall, 4)
    scores["unordered_precision"] = round(precision, 4)
    scores["unordered_f1"] = round(f1, 4)

    scores["overall_score"] = round(
        0.7 * scores["strict_ordered_ratio"] + 0.3 * scores["unordered_f1"], 4
    )

    return scores
```
## Workspace Path

```
workspace/01_Productivity_Flow/task_2_table_tex_download
```

## Skills

```
self-improving-agent-3.0.5
agent-browser
```

## Env

```
```

## Warmup
```
npm install -g agent-browser
```
