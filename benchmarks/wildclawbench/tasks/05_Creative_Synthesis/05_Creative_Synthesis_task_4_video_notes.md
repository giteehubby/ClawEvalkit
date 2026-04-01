---
id: 05_Creative_Synthesis_task_4_video_notes
name: Video Lecture Notes Generation
category: 05_Creative_Synthesis
timeout_seconds: 1200
---

## Prompt

There's an LLM lecture video at `/tmp_workspace/video.mp4`. Can you watch it and put together study notes for me? I want to be able to review the material later without rewatching the whole thing.

Please watch this video carefully and produce a **comprehensive set of study notes** summarizing its content.

### Output Requirements

- Save the notes as `/tmp_workspace/results/notes.md`
- Format: Markdown
- Length: at least 800 words, no more than 3000 words

If you need video understanding or multimodal capabilities, you can call the OpenRouter API (base_url available via the `OPENROUTER_BASE_URL` environment variable, API key available via the `OPENROUTER_API_KEY` environment variable).

## Expected Behavior

The agent should:

1. Watch/analyze the video to understand its full content
2. Identify the main topics and their logical flow
3. Extract key concepts, definitions, examples, and numbers
4. Organize everything into well-structured Markdown notes
5. Ensure completeness — all major ideas from the video are represented

## Grading Criteria

The notes are graded against 8 factual checkpoints extracted from the video's ground truth content, organized into the video's three main sections.

### Part 1 — What is an LLM? (Checkpoints 1–2)

- [ ] CP1: LLM is defined as a mathematical function that predicts the next word/token; it outputs a probability distribution over all possible next words, not a single deterministic answer
- [ ] CP2: Chatbots work by prepending a system prompt + appending the user's message + repeatedly predicting the next word; sampling from less likely words makes output more natural and non-deterministic

### Part 2 — How does an LLM predict the next word? (Checkpoints 3–5)

- [ ] CP3: Model behavior is determined by parameters/weights — large models have hundreds of billions of them; models are trained on enormous internet text
- [ ] CP4: Pre-training: feed all-but-the-last word, compare prediction with the actual last word; backpropagation adjusts parameters; parameters start random (gibberish) and are iteratively refined
- [ ] CP5: RLHF (Reinforcement Learning from Human Feedback): workers flag unhelpful or problematic predictions; their corrections further change the model's parameters to align preferences

### Part 3 — Transformers (Checkpoints 6–8)

- [ ] CP6: Before 2017, models processed text one word at a time; Google introduced transformers which enable parallelization
- [ ] CP7: Each word is converted into a vector/embedding; the attention mechanism lets these vectors communicate and refine meanings based on context
- [ ] CP8: Feed-forward networks (MLPs) provide additional capacity to store language patterns; the model's behavior is an emergent phenomenon from parameter tuning, making it hard to explain specific predictions

### Structural Quality

- [ ] Notes are in valid Markdown with clear headings
- [ ] Length is within the 800–3000 word range
- [ ] Notes are well-organized and logically structured

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the video lecture notes task by checking factual checkpoints via LLM-as-judge.

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    import os
    import json
    from pathlib import Path

    grading_model = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")
    workspace = Path("/tmp_workspace/results")
    notes_path = workspace / "notes.md"

    scores = {}
    zero = {f"cp_{i}": 0.0 for i in range(1, 9)}
    zero.update({"checkpoint_avg": 0.0, "overall_score": 0.0})

    # ========== 1. Pre-checks ==========
    if not notes_path.exists() or notes_path.stat().st_size == 0:
        scores.update(zero)
        return scores

    notes_content = notes_path.read_text(encoding="utf-8")
    word_count = len(notes_content.split())

    # ========== 2. Checkpoint evaluation via LLM-as-judge ==========
    checkpoints = {
        "cp_1": "The notes define an LLM as a mathematical function that predicts the next word/token; it outputs a probability distribution over all possible next words, not a single deterministic answer.",
        "cp_2": "The notes describe how chatbots work by prepending a system prompt + appending the user's message + repeatedly predicting the next word; sampling from less likely words makes output more natural and non-deterministic.",
        "cp_3": "The notes explain that model behavior is determined by parameters/weights, large models have hundreds of billions of them, and models are trained on enormous internet text.",
        "cp_4": "The notes describe pre-training: feed all-but-the-last word, compare prediction with the actual last word; backpropagation adjusts parameters; parameters start random (gibberish) and are iteratively refined.",
        "cp_5": "The notes explain RLHF (Reinforcement Learning from Human Feedback): workers flag unhelpful or problematic predictions, and their corrections further change the model's parameters to align preferences.",
        "cp_6": "The notes mention that before 2017, models processed text one word at a time; Google introduced transformers which enable parallelization.",
        "cp_7": "The notes explain that each word is converted into a vector/embedding; the attention mechanism lets vectors communicate and refine meanings based on context.",
        "cp_8": "The notes mention feed-forward networks (MLPs) providing additional capacity to store language patterns; the model's behavior is an emergent phenomenon from parameter tuning, making it hard to explain specific predictions.",
    }

    cp_scores = {}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ["OPENROUTER_BASE_URL"])

        checkpoint_list = "\n".join(
            f"- **{key}**: {desc}" for key, desc in checkpoints.items()
        )

        prompt = (
            "You are a STRICT grading assistant. Below are study notes about Large Language Models. "
            "Your job is to verify whether the notes reflect SPECIFIC content from the source video, "
            "not just generic textbook knowledge about LLMs.\n\n"
            "IMPORTANT grading rules:\n"
            "- Each checkpoint contains multiple specific claims. ALL claims must be present for full marks.\n"
            "- Generic/vague statements that happen to overlap with a checkpoint should score 0.3 or below.\n"
            "- If any specific claim within a checkpoint is missing, deduct proportionally.\n"
            "- If information is incorrect or contradicts the checkpoint, score 0.0.\n"
            "- Only give 1.0 if every detail in the checkpoint is clearly and accurately covered.\n\n"
            "=== STUDENT NOTES ===\n"
            f"{notes_content}\n"
            "=== END NOTES ===\n\n"
            "Score each checkpoint from 0.0 to 1.0:\n\n"
            f"{checkpoint_list}\n\n"
            "Also evaluate:\n"
            "- **structure_quality**: Are the notes well-organized with clear headings, "
            "logical flow, and readable formatting? (0.0 to 1.0)\n\n"
            "Respond strictly in JSON format with no other content. Example:\n"
            '{"cp_1": 1.0, "cp_2": 0.5, ..., "cp_8": 0.0, "structure_quality": 0.8}'
        )

        resp = client.chat.completions.create(
            model=grading_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.strip("`").removeprefix("json").strip()
        cp_scores = json.loads(raw)
    except Exception as e:
        scores["llm_error"] = str(e)

    for key in checkpoints:
        scores[key] = round(float(cp_scores.get(key, 0.0)), 4)
    scores["structure_quality"] = round(float(cp_scores.get("structure_quality", 0.0)), 4)

    # ========== 3. Overall score ==========
    checkpoint_avg = sum(scores[f"cp_{i}"] for i in range(1, 9)) / 8.0
    scores["checkpoint_avg"] = round(checkpoint_avg, 4)

    # Length penalty: discount if outside 800-3000 word range
    if word_count < 800:
        length_penalty = max(0.0, word_count / 800)
    elif word_count > 3000:
        length_penalty = max(0.0, 1.0 - (word_count - 3000) / 3000)
    else:
        length_penalty = 1.0

    scores["overall_score"] = round(
        (0.85 * checkpoint_avg + 0.15 * scores["structure_quality"]) * length_penalty, 4
    )

    return scores
```
## Workspace Path

```
workspace/05_Creative_Synthesis/task_4_video_notes
```
## Skills
```
video-frames
```
## Env

```
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
JUDGE_MODEL
```
## Warmup
```bash
pip install openai
apt-get update && apt-get install -y ffmpeg
```
