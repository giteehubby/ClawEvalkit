---
id: 02_Code_Intelligence_task_7_connect_the_dots_medium_img_zh
name: Connect the Dots (Medium) — Only Image
category: 02_Code_Intelligence
timeout_seconds: 1200
---

## Prompt

这是一道连点成线谜题。请你完成以下任务（注意：时间有限，尽量15分钟内完成，请注意高效）：
1. 分析输入图片，找出所有带编号的点及其位置坐标。
2. 编写代码，按编号顺序（1→2→3→…→最后一个）用线段依次连接相邻编号的点。
3. 将连线完成后的图片保存。

输入图片路径：`/tmp_workspace/input/origin.png`

要求：
1. `/tmp_workspace/results/result.png`：连线完成后的图片（在原图上按编号顺序用线段连接所有点后的结果）

如果需要图像理解或多模态生成能力，可以调用 OpenRouter API（base_url 通过环境变量 `OPENROUTER_BASE_URL` 获取，API Key 通过环境变量 `OPENROUTER_API_KEY` 获取）。

## Expected Behavior

评测方预期智能体会：

1. 读取 `/tmp_workspace/input/origin.png` 中的连点图。
2. 借助视觉/OCR 等方式识别各编号与坐标。
3. 使用 Python（如 PIL、matplotlib、OpenCV 等）按序连线。
4. 将连线结果保存为 `/tmp_workspace/results/result.png`。

## Grading Criteria

评分规则：

- 文件存在分（30%）：`result.png` 存在即得 0.3 分
- 图片完成度（70%）：VLM 对比 `results/result.png` 与标准答案 `gt/gt.png` 的连线相似度，打分 0-10 分后归一化，占 0.7 权重

`overall_score = 0.3 × file_exists + 0.7 × image_judge_score`

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Connect-the-dots (medium) image-only grading.

    - File existence (30%): result.png exists = 0.3
    - Image completeness (70%): VLM compares results/result.png with gt/gt.png, 0.7 weight
    """
    import os
    import json
    import base64
    import logging
    import time
    from pathlib import Path

    log = logging.getLogger("grade_connect_the_dots_medium_img")
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    base = Path("/tmp_workspace")
    result_image = base / "results" / "result.png"
    gt_image = base / "gt" / "gt.png"

    scores = {}
    image_score = 0.0
    file_exists_score = 0.0

    # ========== OpenAI client initialization ==========
    client = None
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.environ["OPENROUTER_BASE_URL"],
        )
    except Exception as e:
        log.error("OpenAI client initialization failed: %s", e)

    # ========== Image completeness score ==========
    if not result_image.exists():
        log.warning("result.png not found: %s", result_image)
        scores["image_score"] = 0.0
    elif not gt_image.exists():
        log.warning("gt.png not found: %s", gt_image)
        scores["image_score"] = 0.0
    else:
        file_exists_score = 1.0
        log.info("result.png exists, awarding file existence score 0.3")
        try:
            pred_b64 = base64.b64encode(result_image.read_bytes()).decode("utf-8")
            gt_b64 = base64.b64encode(gt_image.read_bytes()).decode("utf-8")

            if client:
                vlm_prompt = (
                    "你是一位评分裁判。请比较以下两张图片的相似度和完成度。\n"
                    "第一张图是标准答案（正确的连点成线结果），第二张图是待评估的答案。\n\n"
                    "这是一道连点成线谜题的解答结果。正确的解答应该是：\n"
                    "按编号顺序用线段依次连接所有带编号的点，最终形成一个可辨识的图案。\n\n"
                    "评分标准（0-10 分）：\n"
                    "- 10分：连线结果与标准答案完全一致或几乎完全一致，图案完整还原\n"
                    "- 7-9分：大部分点按正确顺序连接，图案主体清晰可辨，但有少量连线错误或遗漏\n"
                    "- 4-6分：部分点正确连接，能看出一些图案轮廓，但整体不完整或有较多错误\n"
                    "- 1-3分：只有少量连线正确，整体与标准答案差距较大\n"
                    "- 0分：完全没有连线、图片为空、或与标准答案完全不相关\n\n"
                    '请只返回一个 JSON 对象，示例：\n'
                    '{"score": 7, "reason": "大部分连线正确但右侧部分有偏差"}'
                )

                max_retries = 3
                for attempt in range(max_retries):
                    log.info("VLM image comparison attempt %d/%d...", attempt + 1, max_retries)
                    try:
                        resp = client.chat.completions.create(
                            model=os.environ.get("JUDGE_MODEL", "openai/gpt-5.4"),
                            messages=[{"role": "user", "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{gt_b64}"}},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{pred_b64}"}},
                                {"type": "text", "text": vlm_prompt},
                            ]}],
                            temperature=0.0,
                            max_tokens=256,
                        )
                        raw = resp.choices[0].message.content.strip()
                        log.info("VLM response: %s", raw[:300])
                        if raw.startswith("```"):
                            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                        result_json = json.loads(raw)
                        raw_score = int(result_json["score"])
                        image_score = round(max(0.0, min(1.0, raw_score / 10.0)), 4)
                        scores["image_judge_reason"] = result_json.get("reason", "")
                        scores["image_judge_method"] = "vlm"
                        log.info("VLM image score: %d/10, reason: %s", raw_score, scores["image_judge_reason"])
                        break
                    except Exception as e:
                        log.warning("VLM image comparison attempt %d failed: %s", attempt + 1, e)
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)

                if "image_judge_method" not in scores:
                    log.warning("VLM image comparison failed all 3 attempts, image score 0")
            else:
                log.warning("OpenAI client unavailable, image score 0")

        except Exception as e:
            log.warning("Image read failed: %s", e)

    scores["image_score"] = image_score
    scores["file_exists_score"] = file_exists_score

    # ========== Total score ==========
    scores["overall_score"] = round(0.3 * file_exists_score + 0.7 * scores["image_score"], 4)
    log.info(
        "Final scores: file_exists=%.1f × 30%% + image=%.4f × 70%% = overall=%.4f",
        file_exists_score, scores["image_score"], scores["overall_score"]
    )

    return scores
```
## Workspace Path

```
workspace/02_Code_Intelligence/task_7_connect_the_dots_medium_img_zh
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
pip install openai Pillow numpy
```
