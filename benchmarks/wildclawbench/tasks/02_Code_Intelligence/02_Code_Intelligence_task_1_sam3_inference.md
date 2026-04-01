---
id: 02_Code_Intelligence_task_1_sam3_inference
name: SAM3 Inference Code Implementation
category: 02_Code_Intelligence
timeout_seconds: 1200
---

## Prompt

你是一名 AI 编程专家。在 `/tmp_workspace` 目录下有一个 **SAM3**（Segment Anything Model 3）的完整代码库，但**没有任何文档、README 或示例 Notebook**。你需要通过阅读源代码，理解 SAM3 的使用方法，然后编写推理脚本完成以下 4 个目标检测用例。

### 任务

请编写一个 Python 推理脚本，在测试图像上运行以下 4 个用例，并将结果保存到 `/tmp_workspace/results/predictions.json`。

### 关键信息

- **Python 环境**: `~/miniconda3/envs/eval`
- **SAM3 代码库**: `/tmp_workspace/sam3/`
- **测试图像**: `/tmp_workspace/sam3/assets/images/test_image.jpg`
- **模型权重**: `/tmp_workspace/sam3/sam3.pt`
- **输出文件**: `/tmp_workspace/results/predictions.json`
- **运行设备**: CPU

### 测试用例

你需要实现以下 4 个推理用例：

**用例 1: `text_shoe`** 
- 使用文本提示 `"shoe"` 在图像中检测鞋子
- 置信度阈值：0.5

**用例 2: `single_box`** 
- 使用一个 bounding box：`[480.0, 290.0, 110.0, 360.0]`
- 置信度阈值：0.5

**用例 3: `multi_box`** 
- 使用两个 bounding box：`[[480.0, 290.0, 110.0, 360.0], [370.0, 280.0, 115.0, 375.0]]`
- 对应标签（正/负）：`[True, False]`
- 置信度阈值：0.5

**用例 4: `text_box_combined`** 
- 使用文本提示 `"child"` 和一个 bounding box：`[480.0, 290.0, 110.0, 360.0]`
- 置信度阈值：0.5

### 输出格式

`predictions.json` 必须符合以下 JSON 格式：

```json
{
  "image": "test_image.jpg",
  "image_size": [宽, 高],
  "cases": {
    "text_shoe": {
      "boxes_xyxy": [[x1, y1, x2, y2], ...],
      "scores": [score1, ...]
    },
    "single_box": {
      "boxes_xyxy": [[x1, y1, x2, y2], ...],
      "scores": [score1, ...]
    },
    "multi_box": {
      "boxes_xyxy": [[x1, y1, x2, y2], ...],
      "scores": [score1, ...]
    },
    "text_box_combined": {
      "boxes_xyxy": [[x1, y1, x2, y2], ...],
      "scores": [score1, ...]
    }
  }
}
```

其中 `boxes_xyxy` 是 `[x_min, y_min, x_max, y_max]` 格式的检测框坐标（像素单位），`scores` 是对应的置信度分数。

## Expected Behavior

Agent 应当：

1. 探索 `sam3/` 目录结构，阅读关键源码文件（如 `__init__.py`、`model/sam3_image.py`、`model/sam3_image_processor.py`、`model/box_ops.py` 等）
2. 理解 SAM3 的核心 API：
   - 模型加载方式（如 `build_sam3_image_model`）
   - 处理器创建（如 `Sam3Processor`）
   - 图像设置、文本提示、框提示的 API
   - 检测结果的提取方式
3. 编写推理脚本，正确处理 box 格式转换和坐标归一化
4. 运行脚本，将结果保存到 `/tmp_workspace/results/predictions.json`

## Grading Criteria

- [ ] 成功生成 `predictions.json`，格式正确
- [ ] `text_shoe` 用例通过（F1 ≥ 0.8）
- [ ] `single_box` 用例通过（F1 ≥ 0.8）
- [ ] `multi_box` 用例通过（F1 ≥ 0.8）
- [ ] `text_box_combined` 用例通过（F1 ≥ 0.8）

评分方式：`overall_score = 通过的用例数 / 总用例数`

## Automated Checks

```python
def grade(iou_thresh=0.5, f1_pass=0.8, **kwargs) -> dict:
    """
    Grade the SAM3 inference code writing task.

    Compare predictions.json against gt_boxes.json,
    match by IoU>0.5, then judge pass/fail per case. overall_score = passed / total.

    Returns:
        dict: contains overall_score, passed, total, per_case
    """
    import json
    from pathlib import Path

    workspace_path = kwargs.get("workspace_path", "/tmp_workspace")
    pred_path = Path("/tmp_workspace/results") / "predictions.json"
    gt_path = Path(workspace_path) / "gt" / "gt_boxes.json"

    def _box_iou(a, b):
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter / union if union > 0 else 0.0

    def _match(pred_boxes, gt_boxes):
        used = set()
        tp = 0
        for gt in gt_boxes:
            best_iou, best_j = 0, -1
            for j, p in enumerate(pred_boxes):
                if j in used:
                    continue
                iou = _box_iou(p, gt)
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_iou >= iou_thresh and best_j >= 0:
                used.add(best_j)
                tp += 1
        return tp, len(pred_boxes) - tp, len(gt_boxes) - tp

    def _f1(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return 2*p*r/(p+r) if p+r else 0.0

    if not pred_path.exists():
        return {"path_exists": 0.0, "overall_score": 0.0}

    with open(pred_path) as f:
        pred = json.load(f)
    with open(gt_path) as f:
        gt = json.load(f)

    per_case = {}
    passed = 0
    total = 0

    for name, gt_case in gt["cases"].items():
        gt_boxes = gt_case["boxes_xyxy"]
        pred_boxes = pred.get("cases", {}).get(name, {}).get("boxes_xyxy", [])
        tp, fp, fn = _match(pred_boxes, gt_boxes)
        f1 = _f1(tp, fp, fn)
        case_pass = f1 >= f1_pass
        per_case[name] = {
            "tp": tp, "fp": fp, "fn": fn,
            "f1": round(f1, 4),
            "pass": case_pass,
        }
        if case_pass:
            passed += 1
        total += 1

    return {
        "path_exists": 1.0,
        **{name: 1.0 if case["pass"] else 0.0 for name, case in per_case.items()},
        "overall_score": round(passed / total, 4) if total else 0.0,
    }
```

## Workspace Path

```
workspace/02_Code_Intelligence/task_1_sam3_inference
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
~/miniconda3/envs/eval/bin/pip install numpy==1.26.4 opencv-python==4.9.0.80
```
