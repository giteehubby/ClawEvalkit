"""LLM-as-judge for subjective communication quality scoring."""

from __future__ import annotations

import json
import random
import re
import time

from openai import OpenAI
from pydantic import BaseModel

from ..models.trace import _now


class JudgeResult(BaseModel):
    score: float  # 0.0-1.0
    reasoning: str


_SYSTEM_PROMPT = """\
You are an evaluation judge for an AI assistant.
You will be given a task prompt, a conversation, a summary of actions taken, and a rubric.
Follow the rubric to score the assistant's response on a 0.0-1.0 scale.
Respond with JSON only: {"score": <float>, "reasoning": "<brief explanation>"}
"""

_ACTIONS_SYSTEM_PROMPT = """\
You are an evaluation judge for an AI agent's actions.
You will be given a task prompt, a record of actions the agent actually performed \
(extracted from the server-side audit log, not from the agent's self-report), \
and a rubric.
Follow the rubric to score the quality of the agent's actions on a 0.0-1.0 scale.
Respond with JSON only: {"score": <float>, "reasoning": "<brief explanation>"}
"""

_VISUAL_SYSTEM_PROMPT = """\
You are a STRICT visual evaluation judge. Your job is to compare candidate images \
against reference images and/or a detailed rubric, then assign a score from 0.0 to 1.0.

CRITICAL RULES:
- You must be HARSH and PRECISE. Do NOT give generous scores.
- If the rubric describes specific content (e.g., specific notes, pitches, patterns, \
station names, colors), you MUST verify each detail. Getting the general layout right \
but the specific content wrong should score LOW (0.1-0.3).
- A visually "nice-looking" output that has WRONG content is a FAILURE.
- Only score above 0.5 if the MAJORITY of rubric criteria are clearly satisfied.
- Only score above 0.7 if the content is substantially correct with minor issues.
- Only score above 0.9 if the output is nearly perfect.
- Score 0.0-0.2 if the output is mostly wrong or unrecognizable.
- When reference images are provided, compare the candidate DIRECTLY against them — \
the reference is ground truth.

Respond with JSON only: {"score": <float>, "reasoning": "<brief explanation>"}
"""


def _is_anthropic_endpoint(base_url: str) -> bool:
    """Check if base_url points to an Anthropic-compatible API."""
    return "/anthropic" in base_url or "anthropic.ai" in base_url


class LLMJudge:
    """Judge communication quality using an LLM via OpenAI or Anthropic-compatible API.

    Automatically detects whether to use the OpenAI SDK or Anthropic SDK based on
    the base_url. URLs containing '/anthropic' use the Anthropic SDK; all others
    use the OpenAI SDK.
    """

    def __init__(
        self,
        model_id: str = "google/gemini-2.5-flash",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self.model_id = model_id
        self._call_log: list[dict] = []
        self._use_anthropic = _is_anthropic_endpoint(base_url)

        if self._use_anthropic:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=api_key or "dummy", base_url=base_url)
            # Wrap messages.create for call counting
            _orig = self._anthropic_client.messages.create
            _log = self._call_log
            def _counting_create(*args, **kwargs):
                result = _orig(*args, **kwargs)
                _log.append({
                    "method": "anthropic.messages.create",
                    "model": kwargs.get("model", getattr(result, "model", "")),
                    "timestamp": _now(),
                })
                return result
            self._anthropic_client.messages.create = _counting_create
        else:
            self.client = OpenAI(api_key=api_key or "dummy", base_url=base_url)
            _orig_create = self.client.chat.completions.create
            _log = self._call_log
            def _counting_create(*args, **kwargs):
                result = _orig_create(*args, **kwargs)
                _log.append({
                    "method": "client.chat.completions.create",
                    "model": kwargs.get("model", getattr(result, "model", "")),
                    "timestamp": _now(),
                })
                return result
            self.client.chat.completions.create = _counting_create

    def _call_api(self, messages: list[dict], *, max_tokens: int = 8192) -> str:
        """Call LLM API and return the text content. Works with both OpenAI and Anthropic."""
        if self._use_anthropic:
            # Separate system message from user/assistant messages
            system_text = ""
            api_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_text += msg["content"]
                else:
                    api_messages.append(msg)

            resp = self._anthropic_client.messages.create(
                model=self.model_id,
                system=system_text or anthropic.NOT_GIVEN,
                messages=api_messages,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            # Extract text from content blocks
            text_parts = []
            for block in resp.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            return "\n".join(text_parts) if text_parts else ""
        else:
            resp = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""

    def _call_api_vision(self, system_prompt: str, content_parts: list[dict], *, max_tokens: int = 8192) -> str:
        """Call LLM API with vision content. Works with both OpenAI and Anthropic."""
        if self._use_anthropic:
            # Convert OpenAI-style content_parts to Anthropic format
            anthropic_content = []
            for part in content_parts:
                if part.get("type") == "text":
                    anthropic_content.append({"type": "text", "text": part["text"]})
                elif part.get("type") == "image_url":
                    # Parse data:image/png;base64,... -> media_type + data
                    url = part["image_url"]["url"]
                    if url.startswith("data:"):
                        header, b64_data = url.split(",", 1)
                        # data:image/png;base64 -> image/png
                        media_type = header.split(":")[1].split(";")[0]
                        anthropic_content.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                        })

            resp = self._anthropic_client.messages.create(
                model=self.model_id,
                system=system_prompt,
                messages=[{"role": "user", "content": anthropic_content}],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            text_parts = []
            for block in resp.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            return "\n".join(text_parts) if text_parts else ""
        else:
            resp = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""

    @staticmethod
    def _parse_json_response(raw: str) -> tuple[float, str]:
        """Parse score and reasoning from raw LLM response. Raises on failure."""
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        m = re.search(r'\{[^{}]*\}', raw)
        if m:
            raw = m.group(0)
        try:
            parsed = json.loads(raw)
            return parsed["score"], parsed["reasoning"]
        except (json.JSONDecodeError, KeyError):
            score_m = re.search(r'"score"\s*:\s*([0-9.]+)', raw)
            reason_m = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            if score_m:
                return float(score_m.group(1)), reason_m.group(1) if reason_m else ""
            raise json.JSONDecodeError("No score found in raw", raw, 0)

    def _retry_loop(self, call_fn, method_name: str, log_extra: dict) -> JudgeResult:
        """Generic retry loop shared by all evaluate methods."""
        max_retries = 15
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw = call_fn()
                score, reasoning = self._parse_json_response(raw)
                result = JudgeResult(
                    score=max(0.0, min(1.0, float(score))),
                    reasoning=str(reasoning),
                )
                self._call_log.append({
                    "method": method_name,
                    "score": result.score,
                    "reasoning": result.reasoning,
                    "timestamp": _now(),
                    **log_extra,
                })
                return result
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                delay = min(2 ** (attempt + 1), 8) + random.uniform(0, 1)
                print(f"[judge-retry] ({status or type(exc).__name__}), "
                      f"attempt {attempt + 1}/{max_retries}, waiting {delay:.1f}s ...")
                time.sleep(delay)
        print(f"[judge] All {max_retries} retries exhausted for {method_name}, returning fallback 0.0")
        return JudgeResult(score=0.0, reasoning=f"Judge failed after {max_retries} retries: {last_exc}")

    def evaluate(
        self,
        task_prompt: str,
        conversation: str,
        actions_summary: str,
        rubric: str,
    ) -> JudgeResult:
        """Evaluate communication quality and return a JudgeResult."""
        user_msg = (
            f"## Task Prompt\n{task_prompt}\n\n"
            f"## Conversation\n{conversation}\n\n"
            f"## Actions Taken\n{actions_summary}\n\n"
            f"## Rubric\n{rubric}"
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return self._retry_loop(
            lambda: self._call_api(messages),
            "evaluate",
            {"rubric_preview": rubric[:300]},
        )

    def evaluate_actions(
        self,
        task_prompt: str,
        artifacts: str,
        rubric: str,
    ) -> JudgeResult:
        """Evaluate the quality of agent actions/artifacts from audit log."""
        user_msg = (
            f"## Task Prompt\n{task_prompt}\n\n"
            f"## Agent Actions (from server audit log)\n{artifacts}\n\n"
            f"## Rubric\n{rubric}"
        )
        messages = [
            {"role": "system", "content": _ACTIONS_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return self._retry_loop(
            lambda: self._call_api(messages),
            "evaluate_actions",
            {"rubric_preview": rubric[:300]},
        )

    def evaluate_visual(
        self,
        rubric: str,
        reference_images_b64: list[str],
        candidate_images_b64: list[str],
        context: str = "",
    ) -> JudgeResult:
        """Evaluate visual similarity between reference and candidate images."""
        content_parts: list[dict] = []

        header = "## Visual Evaluation\n"
        if context:
            header += f"{context}\n\n"
        header += f"## Rubric\n{rubric}\n\n"
        header += (
            "## Scoring Calibration\n"
            "- 0.0-0.2: Output is mostly wrong, unrecognizable, or missing most required content\n"
            "- 0.2-0.4: Some elements present but major content errors (wrong notes, wrong colors, wrong layout)\n"
            "- 0.4-0.6: General structure is right but significant content inaccuracies remain\n"
            "- 0.6-0.8: Most content is correct with some minor issues\n"
            "- 0.8-1.0: Content is substantially correct, matching reference closely\n\n"
            "IMPORTANT: Looking nice is NOT enough. The CONTENT must be accurate. "
            "Check each rubric criterion individually and sum up the weighted scores.\n\n"
        )
        header += "Below are reference images followed by candidate images.\n"
        header += 'Respond with JSON only: {"score": <float>, "reasoning": "<brief explanation>"}'
        content_parts.append({"type": "text", "text": header})

        if reference_images_b64:
            content_parts.append({"type": "text", "text": f"\n### Reference ({len(reference_images_b64)} images)"})
            for img_b64 in reference_images_b64:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                })

        if candidate_images_b64:
            content_parts.append({"type": "text", "text": f"\n### Candidate ({len(candidate_images_b64)} images)"})
            for img_b64 in candidate_images_b64:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                })

        return self._retry_loop(
            lambda: self._call_api_vision(_VISUAL_SYSTEM_PROMPT, content_parts),
            "evaluate_visual",
            {
                "rubric_preview": rubric[:300],
                "n_ref_images": len(reference_images_b64),
                "n_cand_images": len(candidate_images_b64),
                "context_preview": context[:200],
            },
        )

    def get_call_log(self) -> list[dict]:
        return list(self._call_log)

    def reset_call_log(self) -> None:
        self._call_log.clear()
