---
id: 02_Code_Intelligence_task_4_jigsaw_puzzle_medium_zh
name: Medium Jigsaw Puzzle — 4×4 Pieces, Filter, Rectify, and Reassemble
category: 02_Code_Intelligence
timeout_seconds: 1200
---

## Prompt

`/tmp_workspace/input/` 目录下有 24 张图片碎片（`piece_01.png` 到 `piece_24.png`），每张碎片的尺寸相同（150×150 像素）。

这些碎片来自一张被切成 **4×4 = 16 块**的正方形原图（600×600 像素），但存在以下两个难点：

1. **干扰碎片**：24 张碎片中混入了 **8 张不属于原图网格的干扰碎片**。这些干扰碎片取自同一张原图的非网格对齐区域（偏移裁切），因此在风格和内容上与正确碎片高度相似，但边缘无法与任何正确碎片对齐。
2. **碎片旋转**：16 张正确碎片中，有 5 张被施加了顺时针旋转——其中 2 张旋转了 90°、1 张旋转了 180°、2 张旋转了 270°，其余 11 张朝向正确。你需要检测这些旋转并在拼接前将碎片还原到正确朝向。

原图是一张朝向正常的图片（人物直立、文字正向可读），不存在整体旋转或翻转。

请你完成以下任务（注意：时间有限，尽量12分钟内完成，请注意高效）：

1. 分析所有 24 张碎片图片，判断哪 16 张属于原图的 4×4 网格、哪 8 张是干扰项。
2. 对于正确的 16 张碎片，检测每张碎片是否被旋转，将其还原到正确朝向。
3. 将还原后的 16 张碎片放到 4×4 网格中的正确位置，拼成完整图片。
4. 将拼好的完整图片保存下来，并描述它画的是什么。

**要求：**

1. 将拼好的完整图片（600×600）保存为：`/tmp_workspace/results/assembled.png`
2. 将结果写入 `/tmp_workspace/results/result.json`，格式如下：

```json
{
  "grid": [
    ["piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png"],
    ["piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png"],
    ["piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png"],
    ["piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png"]
  ],
  "transforms": {
    "piece_XX.png": "rotate_90",
    "piece_XX.png": "rotate_180"
  },
  "distractors": ["piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png", "piece_XX.png"],
  "description": "拼好后的图片是……（中文描述）"
}
```

其中：
- `grid` 是一个 4×4 的二维数组，`grid[行][列]` 对应该位置的碎片文件名（使用原始文件名），行列均从 0 开始（即 `grid[0][0]` 是左上角，`grid[3][3]` 是右下角）。
- `transforms` 是一个对象，记录被旋转的碎片及其旋转角度。键为碎片文件名，值为该碎片被施加的顺时针旋转角度（`"rotate_90"`、`"rotate_180"` 或 `"rotate_270"`）。未被旋转的碎片不需要列出。拼接时应先对这些碎片执行逆旋转再放入网格。
- `distractors` 是 8 张干扰碎片的文件名列表。
- `description` 是对拼好后完整图片的中文描述。

如果需要图像理解或多模态生成能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API Key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

评测方预期智能体会：

1. 读取 `/tmp_workspace/input/` 下所有 24 张碎片图片。
2. 分析碎片，判断哪 16 张属于原图网格、哪 8 张是干扰项。由于干扰碎片取自同一原图的偏移裁切区域，简单的颜色/风格匹配无法区分。常见的有效策略包括：
   - **精确边缘像素匹配**：比较所有碎片对之间的边缘像素行/列，计算 SSD（Sum of Squared Differences）或相关系数。正确碎片对的相邻边缘会有极高的像素一致性（接近完美匹配），而干扰碎片由于偏移裁切，边缘永远无法与任何碎片精确对齐。
   - **变换检测**：对每对碎片的边缘匹配尝试 4 种朝向（0°、90°、180°、270°），找到使边缘一致性最高的旋转角度。
   - **全局优化**：找到一组 16 块碎片及其各自的朝向，使得 4×4 网格中所有相邻边缘的总匹配分数最高。
3. 识别并排除 8 张干扰碎片。
4. 对被旋转的碎片执行逆旋转，还原正确朝向。
5. 将 16 张还原后的碎片拼回 4×4 网格的正确位置。
6. 编写代码将碎片按 grid 位置拼接为 600×600 图片，保存为 `/tmp_workspace/results/assembled.png`。
7. 观察拼好后的完整图片，写出中文描述。
8. 将结果写入 `/tmp_workspace/results/result.json`。

## Grading Criteria

评分满分 34 分，归一化为 0.0～1.0：

- **Grid 位置（16 分）**：每个正确位置 1 分
- **Transforms 旋转检测（5 分）**：每个正确的 key:value 1 分；若模型给出的 transforms 数量 ≠ 5，该维度直接 0 分
- **Distractors 干扰识别（8 分）**：每个正确的干扰项 1 分；若模型给出的 distractors 数量 ≠ 8，该维度直接 0 分
- **拼接图片（5 分）**：`assembled.png` 存在、尺寸为 600×600、且经 VLM 确认为有效的 4×4 拼接图片即得 5 分

`overall_score = 总得分 / 34`

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Medium difficulty jigsaw puzzle grading (max 34 points, normalized to 0-1).

    - Grid positions:  16 pts (1 pt per correct position)
    - Transforms:      5 pts (1 pt per correct key:value; 0 if count != 5)
    - Distractors:     8 pts (1 pt per correct distractor; 0 if count != 8)
    - Assembled image: 5 pts (VLM checks if assembled.png is a valid 4x4 puzzle)
    """
    import os
    import json
    import base64
    import logging
    from pathlib import Path
    from PIL import Image

    log = logging.getLogger("grade_jigsaw_puzzle_medium")
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    TOTAL_POINTS = 34
    base = Path("/tmp_workspace")
    result_file = base / "results" / "result.json"
    assembled_path = base / "results" / "assembled.png"

    gt_solution = {
        (0, 0): "piece_22.png", (0, 1): "piece_11.png", (0, 2): "piece_16.png", (0, 3): "piece_23.png",
        (1, 0): "piece_18.png", (1, 1): "piece_02.png", (1, 2): "piece_14.png", (1, 3): "piece_20.png",
        (2, 0): "piece_21.png", (2, 1): "piece_15.png", (2, 2): "piece_06.png", (2, 3): "piece_08.png",
        (3, 0): "piece_12.png", (3, 1): "piece_05.png", (3, 2): "piece_09.png", (3, 3): "piece_01.png",
    }
    gt_transforms = {
        "piece_02.png": "rotate_90",
        "piece_08.png": "rotate_180",
        "piece_09.png": "rotate_270",
        "piece_12.png": "rotate_270",
        "piece_16.png": "rotate_90",
    }
    gt_distractors = {
        "piece_03.png", "piece_04.png", "piece_07.png", "piece_10.png",
        "piece_13.png", "piece_17.png", "piece_19.png", "piece_24.png",
    }

    scores = {}
    points = 0

    # ========== Read prediction results ==========
    if not result_file.exists():
        log.warning("result.json not found: %s", result_file)
        scores["overall_score"] = 0.0
        return scores

    try:
        pred = json.loads(result_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.warning("result.json JSON parse failed: %s", e)
        scores["overall_score"] = 0.0
        return scores

    pred_grid = pred.get("grid", [])
    pred_transforms = pred.get("transforms", {})
    pred_distractors = list(pred.get("distractors", []))

    # ========== Grid positions (16 points) ==========
    grid_points = 0
    for r in range(4):
        for c in range(4):
            try:
                if pred_grid[r][c] == gt_solution[(r, c)]:
                    grid_points += 1
            except (IndexError, TypeError):
                pass

    scores["grid_points"] = grid_points
    points += grid_points
    log.info("Grid: %d/16 points", grid_points)

    # ========== Transforms (5 points) ==========
    if len(pred_transforms) != 5:
        transforms_points = 0
        log.info("Transforms: count %d ≠ 5, scoring 0 for this dimension", len(pred_transforms))
    else:
        transforms_points = 0
        for piece_name, gt_t in gt_transforms.items():
            if pred_transforms.get(piece_name) == gt_t:
                transforms_points += 1
        log.info("Transforms: %d/5 points", transforms_points)

    scores["transforms_points"] = transforms_points
    points += transforms_points

    # ========== Distractors (8 points) ==========
    if len(pred_distractors) != 8:
        distractors_points = 0
        log.info("Distractors: count %d ≠ 8, scoring 0 for this dimension", len(pred_distractors))
    else:
        pred_distractors_set = set(pred_distractors)
        distractors_points = len(pred_distractors_set & gt_distractors)
        log.info("Distractors: %d/8 points", distractors_points)

    scores["distractors_points"] = distractors_points
    points += distractors_points

    # ========== Assembled image (5 points) — VLM checks if valid 4×4 puzzle ==========
    assembly_points = 0
    if not assembled_path.exists():
        log.info("assembled.png not found, assembly dimension scores 0")
    else:
        try:
            img = Image.open(assembled_path)
            w, h = img.size
            if w != 600 or h != 600:
                log.info("assembled.png size %dx%d ≠ 600x600, assembly dimension scores 0", w, h)
            else:
                img_b64 = base64.b64encode(assembled_path.read_bytes()).decode("utf-8")
                try:
                    import time
                    from openai import OpenAI

                    client = OpenAI(
                        api_key=os.environ["OPENROUTER_API_KEY"],
                        base_url=os.environ["OPENROUTER_BASE_URL"],
                    )

                    vlm_prompt = (
                        "请判断这张图片是否是由多张小图片拼接而成的 4×4 十六宫格图片。\n"
                        "只需要判断是否成功拼接成了一张完整的图片（不需要判断内容是否正确）。\n\n"
                        "判断标准：\n"
                        "- 如果图片看起来是由 16 块碎片拼在一起的（无论内容对不对、朝向对不对），回答 yes\n"
                        "- 如果图片是空白、损坏、不完整、或不是拼接格式，回答 no\n\n"
                        '请只返回 JSON：{"assembled": true} 或 {"assembled": false}'
                    )

                    max_retries = 3
                    for attempt in range(max_retries):
                        log.info("VLM assembly check attempt %d/%d...", attempt + 1, max_retries)
                        try:
                            resp = client.chat.completions.create(
                                model=os.environ.get("JUDGE_MODEL", "openai/gpt-5.4"),
                                messages=[{"role": "user", "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                                    {"type": "text", "text": vlm_prompt},
                                ]}],
                                temperature=0.0,
                                max_tokens=128,
                            )
                            raw = resp.choices[0].message.content.strip()
                            log.info("VLM response: %s", raw[:200])
                            if raw.startswith("```"):
                                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                            vlm_result = json.loads(raw)
                            if vlm_result.get("assembled"):
                                assembly_points = 5
                                log.info("VLM verdict: assembled, assembly dimension scores 5")
                            else:
                                log.info("VLM verdict: not assembled, assembly dimension scores 0")
                            break
                        except Exception as e:
                            log.warning("VLM assembly check attempt %d failed: %s", attempt + 1, e)
                            if attempt < max_retries - 1:
                                time.sleep(2 ** attempt)

                except Exception as e:
                    log.error("OpenAI client initialization failed: %s, assembly dimension scores 0", e)

        except Exception as e:
            log.warning("assembled.png read failed: %s, assembly dimension scores 0", e)

    scores["assembly_points"] = assembly_points
    points += assembly_points

    # ========== Total score ==========
    scores["total_points"] = points
    scores["overall_score"] = round(points / TOTAL_POINTS, 4)

    log.info("Score breakdown: grid=%d + transforms=%d + distractors=%d + assembly=%d = %d/%d → overall=%.4f",
             grid_points, transforms_points, distractors_points, assembly_points,
             points, TOTAL_POINTS, scores["overall_score"])

    return scores
```
## Workspace Path

```
workspace/02_Code_Intelligence/task_4_jigsaw_puzzle_medium_zh
```
## Skills
```
```
## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```
## Warmup
```
pip install openai Pillow
```
