---
id: 01_Productivity_Flow_task_8_real_image_category
name: Classify Mixed Images into 5 Categories
category: 01_Productivity_Flow
timeout_seconds: 600
---

## Prompt

请处理位于 `/tmp_workspace/images.tar` 的压缩包。

这个压缩包中共有 100 张各类图片，请先解压，再按以下 5 个类别完成分类：

| 类别文件夹名 | 说明 |
|---|---|
| `1_charts_and_tables` | 统计图表与数据表格，如柱状图、折线图、饼图、散点图、数据表格、信息图表等 |
| `2_documents_and_text` | 以文字为主体的图像，如书籍封面、古籍、票据、书法、演示文稿、数学题、流程图、文字海报等 |
| `3_photos_natural_scenes` | 由相机拍摄的真实场景，如动物、人物、街景、风光、室内环境、实物照片等 |
| `4_medical_and_science` | 医学影像或学术科学内容，如 X 光/MRI、内窥镜图像、科学公式、学术论文片段等 |
| `5_synthetic_3d_and_ui` | 计算机生成的图像，如 3D 渲染物体、合成场景、手机/网页 UI 截图等 |

请以以下形式呈现结果：

1. 创建 `/tmp_workspace/results/` 目录。
2. 在 `/tmp_workspace/results/` 下创建 5 个子目录，目录名必须与上表中的类别文件夹名一致。
3. 将压缩包中的所有图片按类别分别放入对应的子目录中。
4. 请保持每张图片原有的文件名不变。

如果需要图像理解或多模态生成能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API Key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

The agent should:

1. Inspect and extract the provided archive
2. View each image and determine which of the 5 categories it belongs to
3. Create `/tmp_workspace/results` with exactly 5 category folders using the specified names
4. Place every image into exactly one folder while preserving the original filenames
5. Avoid extra files or malformed directory structure in the final output

The final score is based on whether the output directory contains the correct partition of images into 5 categories.

## Grading Criteria

- [ ] `/tmp_workspace/results` exists
- [ ] There are exactly 5 immediate subdirectories under `/tmp_workspace/results`
- [ ] All 100 expected image files are present exactly once, with no extra files
- [ ] Each predicted folder is internally pure with respect to image class
- [ ] Each ground-truth class is concentrated into a single predicted folder
- [ ] The overall clustering accuracy under the best one-to-one folder/class matching is high

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the image classification task.

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    import json
    from collections import Counter
    from functools import lru_cache
    from pathlib import Path

    output_dir = Path("/tmp_workspace/results")
    gt_file = Path("/tmp_workspace") / "gt" / "filename_to_class.json"

    ALL_CRITERIA = {
        "output_dir_exists": 0.0,
        "five_subdirs": 0.0,
        "all_expected_files_present": 0.0,
        "no_duplicate_or_extra_files": 0.0,
        "folder_purity": 0.0,
        "class_completeness": 0.0,
        "best_match_accuracy": 0.0,
        "overall_score": 0.0,
    }

    if not gt_file.exists():
        return ALL_CRITERIA

    gt_map = json.loads(gt_file.read_text(encoding="utf-8"))
    expected_files = set(gt_map.keys())
    classes = sorted(set(gt_map.values()))
    total_expected = len(expected_files)

    if total_expected == 0:
        return ALL_CRITERIA

    scores = dict(ALL_CRITERIA)

    if not output_dir.exists() or not output_dir.is_dir():
        return scores

    scores["output_dir_exists"] = 1.0

    pred_dirs = sorted([p for p in output_dir.iterdir() if p.is_dir()])
    scores["five_subdirs"] = 1.0 if len(pred_dirs) == 5 else 0.0

    pred_file_counts = Counter()
    extra_files = []
    pred_sets = []

    for folder in pred_dirs:
        folder_files = []
        for item in folder.iterdir():
            if item.is_file():
                folder_files.append(item.name)
            else:
                extra_files.append(str(item))
        pred_sets.append(folder_files)
        pred_file_counts.update(folder_files)

    predicted_files = set(pred_file_counts.keys())
    missing_files = expected_files - predicted_files
    extra_named_files = predicted_files - expected_files
    has_duplicates = any(v != 1 for v in pred_file_counts.values())

    scores["all_expected_files_present"] = 1.0 if not missing_files else 0.0
    scores["no_duplicate_or_extra_files"] = 1.0 if (not extra_named_files and not extra_files and not has_duplicates) else 0.0

    class_to_idx = {name: idx for idx, name in enumerate(classes)}
    matrix = []
    valid_total = 0

    for folder_files in pred_sets:
        row = [0] * len(classes)
        for filename in folder_files:
            cls = gt_map.get(filename)
            if cls is None:
                continue
            row[class_to_idx[cls]] += 1
            valid_total += 1
        matrix.append(row)

    if valid_total > 0 and matrix:
        scores["folder_purity"] = round(
            sum(max(row) for row in matrix) / valid_total,
            4,
        )

        completeness_hits = 0
        for class_idx in range(len(classes)):
            completeness_hits += max(row[class_idx] for row in matrix)
        scores["class_completeness"] = round(completeness_hits / total_expected, 4)

        @lru_cache(maxsize=None)
        def best_match(i: int, used_mask: int) -> int:
            if i == len(matrix):
                return 0

            best = best_match(i + 1, used_mask)
            for class_idx in range(len(classes)):
                if used_mask & (1 << class_idx):
                    continue
                best = max(
                    best,
                    matrix[i][class_idx] + best_match(i + 1, used_mask | (1 << class_idx)),
                )
            return best

        matched = best_match(0, 0)
        scores["best_match_accuracy"] = round(matched / total_expected, 4)

    scores["overall_score"] = round(
        0.06 * scores["five_subdirs"]
        + 0.08 * scores["all_expected_files_present"]
        + 0.06 * scores["no_duplicate_or_extra_files"]
        + 0.8 * scores["best_match_accuracy"],
        4,
    )

    return scores
```

## Workspace Path

```
workspace/01_Productivity_Flow/task_8_real_image_category
```

## Skills

```
```

## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
```

## Warmup

```
```

