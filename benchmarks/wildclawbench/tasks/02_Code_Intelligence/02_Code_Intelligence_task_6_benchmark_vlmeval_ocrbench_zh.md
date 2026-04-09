---
id: 02_Code_Intelligence_task_6_benchmark_vlmeval_ocrbench_zh
name: VLMEvalKit OCRBench Evaluation
category: 02_Code_Intelligence
timeout_seconds: 1200
---

## Prompt

任务：使用 VLMEvalKit 评测模型在 OCRBench 上的表现

【评测目标】
待评测模型：gpt-5-mini-2025-08-07（OpenAI API 模型）
评测基准：OCRBench（原始版本v1，注意不是 OCRBenchV2）

【可复现性要求】
尽可能保证评测结果可复现，比如温度设置等，具体看框架实现，参考框架某些设置可以加速评测

【输出要求】
输出文件路径：/tmp_workspace/results/result.json
输出格式：见下方 JSON 格式规范

result.json 格式规范：
```json
{
  "model": "gpt-5-mini-2025-08-07",
  "benchmark": "OCRBench",
  "Final Score": <int>,
  "Text Recognition": <int>,
  "Scene Text-centric VQA": <int>,
  "Document-oriented VQA": <int>,
  "Key Information Extraction": <int>,
  "Handwritten Mathematical Expression Recognition": <int>
}
```

【相关资源】
1. OpenRouter接口
   - base_url: 从环境变量 `OPENROUTER_BASE_URL` 中获取
   - API Key: 从环境变量 `OPENROUTER_API_KEY` 中获取
2. OCRBench 数据文件
   - 如果评测过程中需要用到 OCRBench 的 TSV 数据文件，可以直接使用 `/tmp_workspace/OCRBench.tsv`，无需另外下载

【提示和注意事项】
1. 我希望用尽可能少的时间得到结果，加速下评测
2. python环境：请使用当前环境中的 `eval` 这个 conda 环境(位置在`/root/miniconda3/envs/eval`)，里面已经预装了一些常用的 python 包，但不保证完全满足 VLMEvalKit 的所有依赖要求，缺少的包请自行在这个环境里安装

## Expected Behavior

评测方预期智能体会：

1. 克隆 VLMEvalKit 仓库并安装依赖。
2. 配置 OpenAI API（API Base + API Key）以调用 gpt-5-mini-2025-08-07。
3. 使用 VLMEvalKit 在 OCRBench（v1）上评测该模型，设置 temperature 等参数保证可复现。
4. 解析评测结果，按指定格式写入 `/tmp_workspace/results/result.json`。

## Grading Criteria

- [ ] 搭建评测环境（如克隆 VLMEvalKit 等） → +0.2 分
- [ ] 正确配置 OpenAI API 接入并调用 gpt-5-mini-2025-08-07
- [ ] 在 OCRBench（v1，非 v2）上完成评测
- [ ] `result.json` 中 Final Score 在 810–835 范围内 → +0.8 分
- 总分 = 环境分 + 结果分，满分 1.0

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    VLMEvalKit OCRBench evaluation task grading (additive).

    Scoring rules:
    - VLMEvalKit cloned (found clone directory under /tmp_workspace/): +0.2
    - result.json Final Score within 810-835 range: +0.8
    - Max score 1.0

    Returns:
        dict containing overall_score (0.0-1.0)
    """
    import json
    import logging
    import os
    from pathlib import Path

    log = logging.getLogger("grade_benchmark_vlmeval_ocrbench")
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    score = 0.0

    def _vlmevalkit_cloned() -> bool:
        """Recursively search /tmp_workspace/ for VLMEvalKit clone directory (case-insensitive)."""
        base = Path("/tmp_workspace")
        if not base.exists():
            return False
        for root, dirs, files in os.walk(base):
            root_lower = os.path.basename(root).lower()
            if "vlmevalkit" in root_lower or "vlmeval" in root_lower:
                if any(f.lower() == "run.py" for f in files):
                    log.info("Found VLMEvalKit clone: %s", root)
                    return True
                if any(d.lower() == "vlmeval" for d in dirs):
                    log.info("Found VLMEvalKit clone: %s", root)
                    return True
        return False

    if _vlmevalkit_cloned():
        score += 0.2
        log.info("VLMEvalKit clone detected, +0.2")
    else:
        log.info("VLMEvalKit clone directory not detected")

    result_file = Path("/tmp_workspace/results/result.json")
    if not result_file.exists():
        log.warning("result.json not found: %s", result_file)
        return {"overall_score": score}

    try:
        result = json.loads(result_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        log.error("result.json parse failed: %s", e)
        return {"overall_score": score}

    final_score = result.get("Final Score")
    if final_score is None:
        log.warning("result.json has no Final Score field")
        return {"overall_score": score}

    try:
        final_score = int(final_score)
    except (ValueError, TypeError):
        log.warning("Final Score is not a valid integer: %s", final_score)
        return {"overall_score": score}

    log.info("Final Score: %d", final_score)

    if 810 <= final_score <= 835:
        score += 0.8
        log.info("Final Score within 810-835 range, +0.8")
    else:
        log.warning("Final Score %d not within 810-835 range", final_score)

    return {"overall_score": score}
```

## Workspace Path

```
workspace/02_Code_Intelligence/task_6_benchmark_vlmeval_ocrbench_zh
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
