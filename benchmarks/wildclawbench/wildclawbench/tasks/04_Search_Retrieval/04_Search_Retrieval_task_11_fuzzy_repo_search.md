---
id: 04_Search_Retrieval_task_11_fuzzy_repo_search
name: Fuzzy Repository Search
category: 04_Search_Retrieval
timeout_seconds: 900
---

## Prompt

Help me find that open-source project from 2023–2024 that made it possible to run large language models on ordinary laptops and desktops without requiring a dedicated GPU. I only vaguely remember a few things about it:

- The project was implemented in a low-level systems programming language (C or C++) for maximum performance, with minimal external dependencies.
- The repository name referenced an animal commonly associated with South America.
- The original creator was also well-known in the community for building a similar lightweight inference tool for a popular open-source speech recognition model.
- The project pioneered a custom quantization file format that became widely adopted by the community.

The GitHub repository should have more than 60k stars.

Save the results into `/tmp_workspace/results/results.md`.

## Expected Behavior

The agent should complete the following tasks:

1. Search the web for open-source projects that enable running LLMs on consumer hardware without GPUs.

2. Identify multiple candidate projects (e.g., llama.cpp, Ollama, llamafile, LocalAI, etc.) and evaluate each against the given clues.

3. Narrow down to the correct project by confirming: (a) it is written in C/C++, (b) the name references a South American animal, (c) the creator also built a speech recognition inference tool (whisper.cpp), and (d) the project introduced a widely-used quantization format (GGUF).

4. Verify the GitHub star count exceeds 60k.

## Grading Criteria

- [ ] Finding the correct repository earns the points.

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    04_Search_Retrieval_task_11_fuzzy_repo_search

    Args:

    Returns:
        0 or 1
    """
    import os
    import json
    import logging
    from pathlib import Path

    log = logging.getLogger("04_Search_Retrieval_task_11_fuzzy_repo_search Grading Start!")
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

        gt_description = "llama.cpp (https://github.com/ggerganov/llama.cpp) by Georgi Gerganov (ggerganov)"
        judge_prompt = f"""你是一位评分裁判。请你依据标准答案和待评估回答进行打分。

具体要求是：
1. 如果待评估回答中找到的项目与标准答案不一致（即不是 llama.cpp），就返回 score 为 0。
2. 如果待评估回答中找到的项目与标准答案一致（即是 llama.cpp，由 ggerganov / Georgi Gerganov 开发），就返回 score 为 1。
3. 请注意：Ollama、llamafile、LocalAI 等项目均不是正确答案。只有 llama.cpp 才是正确答案。

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

    # ---- Fall back when all LLM attempts fail ----
    if not llm_succeeded:
        log.warning("LLM Judge failed all 3 attempts, scoring 0")
        scores["overall_score"] = 0

    log.info("Final score: overall_score=%s",
             scores["overall_score"])

    return scores
```

## Workspace Path

```
workspace/04_Search_Retrieval/task_11_fuzzy_repo_search
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
