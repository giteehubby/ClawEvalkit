---
id: 05_Creative_Synthesis_task_2_goal_highlights
name: Goal Highlights Compilation
category: 05_Creative_Synthesis
timeout_seconds: 1200
---

## Prompt

This is a full first-half video of a La Liga match between Real Betis and FC Barcelona, located at `/tmp_workspace/first_half.mp4`.

Based on this video, compile a **goal highlights reel for Barcelona's #7 Ferran Torres from the first half**.

### Requirements

1. Total highlights duration must be **30 seconds or less**
2. Must include **all** of Ferran Torres's goals from the first half
3. Each goal clip should cover the complete sequence from the start of the attacking play to the ball hitting the net
4. **Do not include post-goal celebrations**
5. Goal clips can be directly concatenated — no transition effects needed
6. Maintain original video quality; do not add text, watermarks, or visual effects

### Output Requirements

- Save the highlights video as `/tmp_workspace/results/highlights.mp4`
- Format: MP4 (H.264 encoding)
- Also save a cut sheet file at `/tmp_workspace/results/cut_sheet.json` documenting each goal clip, in the following format:

```json
[
  {
    "goal_number": 1,
    "source_start": "MM:SS",
    "source_end": "MM:SS",
    "description": "Brief description"
  }
]
```

Where `source_start` and `source_end` are positions in the source video file in "MM:SS" format (e.g., "17:50" to "18:02").

If you need image/video understanding or multimodal capabilities, you can call the OpenRouter API (base_url available via the `OPENROUTER_BASE_URL` environment variable, API key available via the `OPENROUTER_API_KEY` environment variable).

## Expected Behavior

The agent should:

1. Watch/analyze the first-half video to locate all of Ferran Torres's goal moments
2. Determine the time range for each goal from the start of the attacking play to the ball hitting the net
3. Exclude post-goal celebration footage
4. Use ffmpeg or similar tools to trim and concatenate video segments
5. Produce a highlights video with total duration no longer than 30 seconds
6. Generate the cut sheet file `cut_sheet.json`

## Grading Criteria

### Overall Quality

- [ ] `highlights.mp4` file exists and is playable
- [ ] Total duration does not exceed 30 seconds
- [ ] Video format is correct (MP4 / H.264)
- [ ] Clear picture, no black screens, artifacts, or audio-video desync
- [ ] No black screens, artifacts, or audio-video desync between clips

### Content Accuracy

- [ ] Contains all of Ferran Torres's first-half goals
- [ ] Each goal includes the complete sequence from attack initiation to the ball hitting the net
- [ ] Does not include post-goal celebrations
- [ ] `cut_sheet.json` exists and has correct format
- [ ] Timestamps in `cut_sheet.json` are consistent with the actual clips

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the Ferran Torres goal highlights compilation task.

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    import os
    import json
    import subprocess
    from pathlib import Path

    grading_model = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")

    workspace = Path("/tmp_workspace/results")
    scores = {}

    highlights_path = workspace / "highlights.mp4"
    cut_sheet_path = workspace / "cut_sheet.json"

    # ========== 1. File existence checks ==========
    scores["highlights_exists"] = 1.0 if highlights_path.exists() and highlights_path.stat().st_size > 0 else 0.0
    scores["cut_sheet_exists"] = 1.0 if cut_sheet_path.exists() and cut_sheet_path.stat().st_size > 0 else 0.0

    if scores["highlights_exists"] == 0.0:
        scores.update({
            "cut_sheet_completeness": 0.0,
            "content_accuracy": 0.0,
            "overall_score": 0.0,
        })
        return scores

    # ========== 2. Video format and duration checks ==========
    duration = 0.0
    codec = ""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-show_entries", "stream=codec_name",
             "-of", "json", str(highlights_path)],
            capture_output=True, text=True, timeout=15,
        )
        probe = json.loads(result.stdout)
        duration = float(probe.get("format", {}).get("duration", 0))
        streams = probe.get("streams", [])
        codec = streams[0].get("codec_name", "") if streams else ""
    except Exception:
        pass

    # Pre-check: duration and format
    if duration <= 0 or duration > 60:
        scores.update({"cut_sheet_completeness": 0.0, "content_accuracy": 0.0, "overall_score": 0.0})
        return scores

    # ========== 3. cut_sheet.json validation ==========
    cut_sheet_data = []
    expected_goals = [
        {"goal_number": 1, "video_time": 985},
        {"goal_number": 2, "video_time": 1097},
        {"goal_number": 3, "video_time": 2707},
    ]

    if scores["cut_sheet_exists"] == 1.0:
        try:
            cut_sheet_data = json.loads(cut_sheet_path.read_text(encoding="utf-8"))
            if not isinstance(cut_sheet_data, list):
                cut_sheet_data = []
        except (json.JSONDecodeError, Exception):
            cut_sheet_data = []

    def _parse_timestamp(s):
        """Parse 'MM:SS' or raw seconds into total seconds."""
        s = str(s).strip()
        if ':' in s:
            parts = s.split(':')
            try:
                return int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                return None
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    matched_goals = 0
    used_pred_items = set()
    for expected in expected_goals:
        gt_sec = expected["video_time"]
        for idx, item in enumerate(cut_sheet_data):
            if idx in used_pred_items:
                continue
            pred_sec = _parse_timestamp(item.get("source_start", ""))
            if pred_sec is not None and abs(pred_sec - gt_sec) <= 30:
                matched_goals += 1
                used_pred_items.add(idx)
                break

    scores["cut_sheet_completeness"] = round(matched_goals / len(expected_goals), 4)

    # ========== 4. Content accuracy (LLM) ==========
    content_accuracy_score = 0.0

    try:
        import base64
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ["OPENROUTER_BASE_URL"])

        num_samples = min(6, max(3, int(duration)))
        interval = duration / (num_samples + 1)
        frames_b64 = []

        for i in range(1, num_samples + 1):
            ts = interval * i
            frame_path = workspace / f"_tmp_sample_{i}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", str(highlights_path),
                 "-vframes", "1", "-q:v", "2", str(frame_path)],
                capture_output=True, timeout=10,
            )
            if frame_path.exists():
                with open(frame_path, "rb") as f:
                    frames_b64.append(base64.b64encode(f.read()).decode())
                frame_path.unlink(missing_ok=True)

        cut_sheet_summary = ""
        if cut_sheet_data:
            cut_sheet_summary = "Agent's submitted cut sheet:\n"
            for item in cut_sheet_data:
                cut_sheet_summary += (
                    f"  - Goal #{item.get('goal_number', '?')}: "
                    f"source {item.get('source_start', '?')}~{item.get('source_end', '?')}, "
                    f"{item.get('description', '')}\n"
                )

        if frames_b64:
            content_parts = [
                {"type": "text", "text": (
                    "Below are multi-frame samples from a football goal highlights video. "
                    "This highlights reel should feature Barcelona's #7 Ferran Torres's "
                    "goals from the first half, and should not include celebration footage.\n\n"
                    "=== Ground Truth ===\n"
                    "Ferran Torres scored 3 goals in the first half:\n"
                    "  - ~16:25 in source video: Koundé assists, Ferran taps in to equalize\n"
                    "  - ~18:17 in source video: Baldé crosses, Ferran volleys in with an acrobatic finish\n"
                    "  - ~45:07 in source video: Pedri passes, Ferran scores a deflected long-range shot (hat-trick)\n\n"
                    f"{cut_sheet_summary}\n"
                    "Score **content_accuracy** (0.0 – 1.0) by evaluating:\n"
                    "- Can you see goal-scoring scenes (shots on goal, ball hitting the net, etc.)?\n"
                    "- Does it feature the correct player (#7 jersey)?\n"
                    "- Are the agent's submitted clip times (source_start/source_end) "
                    "roughly consistent with the ground truth video timestamps (within ±30 seconds is considered correct)?\n"
                    "- Is there any celebration footage (celebrations should result in deductions)?\n\n"
                    "Respond strictly in the following JSON format with no other content:\n"
                    '{"content_accuracy": 0.0}'
                )},
            ]
            for b64 in frames_b64:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })

            resp = client.chat.completions.create(
                model=grading_model,
                messages=[{"role": "user", "content": content_parts}],
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            raw = raw.strip("`").removeprefix("json").strip()
            llm_scores = json.loads(raw)
            content_accuracy_score = float(llm_scores.get("content_accuracy", 0.0))
    except Exception as e:
        scores["llm_error"] = str(e)

    scores["content_accuracy"] = round(content_accuracy_score, 4)

    # ========== 5. Overall score ==========
    # Penalty if duration exceeds 30s limit
    duration_penalty = 1.0 if duration <= 30 else max(0.0, 1.0 - (duration - 30) / 30)
    scores["overall_score"] = round(
        (0.30 * scores["cut_sheet_completeness"] + 0.70 * scores["content_accuracy"]) * duration_penalty, 4
    )

    return scores
```
## Workspace Path

```
workspace/05_Creative_Synthesis/task_2_goal_highlights
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
