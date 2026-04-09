---
id: 04_Search_Retrieval_task_3_constraint_search
name: Constraint-Based Planning Search
category: 04_Search_Retrieval
timeout_seconds: 900
---

## Prompt

我想购买一部手机，请根据以下条件找出最符合的型号：

手机条件：
1. 品牌来自 中国厂商
2. 使用 骁龙 8 Gen 3
3. 主摄 1英寸传感器
4. 支持 卫星通信
5. 发布时间 2024
6. 内存 512 GB
7. 电池 5400mAh以上

请给出：
1. 给我推荐符合以上要求的手机
2. 结果保存为.md文件，保存到 `/tmp_workspace/results/results.md`

## Expected Behavior

1. The agent should first determine that no phone fully satisfies all the conditions.

2. The agent should then recommend several phones that come very close to meeting the conditions.

## Grading Criteria

- [ ] Find that no phone fully satisfies all the conditions
- [ ] Recommend several phones that come very close to meeting the conditions

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_3_constraint_search

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_3_constraint_search Grading Start!")
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    description_file = Path("/tmp_workspace/results/results.md")
    scores = {}

    if not description_file.exists():
        log.warning("results.md not found: %s", description_file)
        scores["overall_score"] = 0.0
        return scores

    pred_description = description_file.read_text(encoding="utf-8").strip()
    if not pred_description:
        log.warning("results.md is empty")
        scores["overall_score"] = 0.0
        return scores

    log.info("Content in MD: %s", pred_description[:200])

    llm_succeeded = False
    last_error = None

    try:
        import time
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.environ["OPENROUTER_BASE_URL"],
        )

        judge_prompt = f"""你是一位评分裁判, 请你依据“评分标准”为“模型回答”进行打分。

评分标准：
1. 如果“模型回答”发现了不存在任何一款手机符合全部要求，且推荐了一些满足大部分要求的手机型号，（这些手机型号至少包括 Xiaomi 14 Ultra / Vivo X100 Ultra / Magic 6 至臻版 / OPPO Find X7 Ultra 中的两种），则返回  score 为 1。
2. 如果“模型回答”发现了不存在任何一款手机符合全部要求，且没有推荐一些满足大部分要求的其他手机型号，则返回  score 为 0.5。
3. 如果“模型回答”没有发现不存在任何一款手机符合全部要求，或者误以为某一款手机符合全部要求，则返回 score 为 0。

【模型回答】
{pred_description}

请只返回一个 JSON 对象，格式：{{"score": <0-1>, "reason": "<简要理由>"}}"""

        max_retries = 3
        for attempt in range(max_retries):
            log.info("LLM Judge request %d/%d...", attempt + 1, max_retries)
            try:
                response = client.chat.completions.create(
                    model=os.environ.get("JUDGE_MODEL", "openai/gpt-5.4"),
                    messages=[{"role": "user", "content": judge_prompt}],
                    temperature=0,
                )

                result_text = response.choices[0].message.content.strip()
                log.info("LLM raw response: %s", result_text[:300])

                if result_text.startswith("```"):
                    result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                result_json = json.loads(result_text)
                raw_score = float(result_json.get("score", 0))
                scores["overall_score"] = raw_score
                scores["judge_reason"] = result_json.get("reason", "")
                llm_succeeded = True
                log.info("LLM Judge succeeded — score: %s, reason: %s",
                         raw_score, scores["judge_reason"])
                break

            except Exception as e:
                last_error = e
                log.warning("LLM Judge attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

    except Exception as e:
        last_error = e
        log.error("OpenAI client initialization failed: %s", e)

    if not llm_succeeded and last_error:
        scores["judge_error"] = str(last_error)

    # ---- Fall back to keyword matching when all LLM attempts fail ----
    if not llm_succeeded:
        log.warning("LLM Judge failed all 3 attempts, scoring 0")
        scores["overall_score"] = 0

    log.info("Final score: overall_score=%s",
             scores["overall_score"])

    return scores
```
## Workspace Path

```
workspace/04_Search_Retrieval/task_3_constraint_search
```
## Skills

```
agent-browser
```

## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```

## Warmup

```
npm install -g agent-browser
```

