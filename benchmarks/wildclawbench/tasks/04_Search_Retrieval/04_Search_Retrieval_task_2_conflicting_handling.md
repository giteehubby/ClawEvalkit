---
id: 04_Search_Retrieval_task_2_conflicting_handling
name: Conflicting Information Handling between Local Data and Web
category: 04_Search_Retrieval
timeout_seconds: 900
---

## Prompt

During the Paris Olympics, Company A in China sold a batch of sports equipment to domestic Company B for use in Company B’s export business. The parties agreed that Company B should pay for the goods within 30 days after delivery. However, after receiving the goods, Company B never made payment.

In August of the same year, Company B confirmed by email that it still owed RMB 500,000 in payment and promised to pay as soon as possible.

After that, the parties engaged in multiple rounds of collection and negotiation, but the debt remained unpaid.

In September of the same year, I am a lawyer preparing to file a lawsuit on behalf of Company A to recover the payment. My question is: what is the statute of limitations for this claim?

Write your analysis into `/tmp_workspace/results/results.md`.

The legal materials in my repository are case-handling reference provisions compiled by our law firm. Please complete the task by referring to these files. These legal provisions are located in the following folder: `/tmp_workspace/04_Search_Retrieval_task_2_conflicting_handling/laws`

## Expected Behavior

1. The agent should first read the locally stored legal provisions to identify the basis for resolving the issue.

2. The agent should then recognize that some of the provisions may be outdated and verify them on the Internet.

3. Finally, the agent needs to resolve any conflicts between the local information and the online information, and return the correct answer.

## Grading Criteria

- [ ] Points are awarded if the answer is right.

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_2_conflicting_handling

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_2_conflicting_handling Grading Start!")
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

        gt_description = "3 years"
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答给出的最后推理答案认为有效期是 3 years（和标准答案一致），score 为 1。
2. 如果待评估回答给出的最后推理答案是其他年份，就返回 score 为 0。

【标准答案】
{gt_description}

【待评估回答】
{pred_description}

请只返回一个 JSON 对象，格式：{{"score": <0或1>, "reason": "<简要理由>"}}"""

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
workspace/04_Search_Retrieval/task_2_conflicting_handling
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

