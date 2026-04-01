"""
ZClawBench Judge 评分逻辑。

使用 Judge Model (LLM Judge) 对轨迹进行评估，
评估维度: Task Completion, Tool Usage, Reasoning, Answer Quality。
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .judge_prompt import JUDGE_PROMPT, JUDGE_PROMPT_OFFLINE

logger = logging.getLogger("zclawbench.grading")


@dataclass
class JudgeScore:
    """Judge 评分结果"""
    task_id: str
    model: str  # 被评估的模型名
    task_completion: float
    tool_usage: float
    reasoning: float
    answer_quality: float
    overall_score: float
    justification: str
    raw_response: str = ""


def get_ark_key() -> str:
    """从环境变量读取 ARK API Key"""
    return os.environ.get("JUDGE_API_KEY", "")


def _trajectory_to_text(trajectory: List[Dict], max_turns: int = 30) -> str:
    """将轨迹转换为可读文本（限制长度）"""
    turns = []
    for i, msg in enumerate(trajectory[:max_turns]):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "?")
        content = msg.get("content", [])
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        parts.append(c.get("text", ""))
                    elif c.get("type") == "tool_use":
                        parts.append(f"[TOOL: {c.get('name')} | INPUT: {json.dumps(c.get('input', {}), ensure_ascii=False)[:200]}]")
                    elif c.get("type") == "tool_result":
                        result = c.get("content", "")
                        parts.append(f"[TOOL_RESULT: {str(result)[:200]}]")
                    elif c.get("type") == "thinking":
                        parts.append(f"[THINKING: {str(c.get('thinking', ''))[:200]}]")
                elif isinstance(content, str):
                    parts.append(str(content))
            text = " ".join(parts)
        elif isinstance(content, str):
            text = content
        else:
            text = str(content)
        turns.append(f"{role.upper()}: {text[:500]}")

    return "\n\n".join(turns)


def _parse_judge_response(response_text: str) -> Optional[Dict[str, Any]]:
    """从 Judge 模型响应中解析 JSON 评分"""
    # 尝试提取 JSON
    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    # 尝试整段解析
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    return None


def _call_judge_with_retry(
    client,
    judge_model: str,
    messages: List[Dict],
    max_retries: int = 5,
    base_delay: float = 5.0,
) -> Optional[str]:
    """调用 Judge 模型，带指数退避重试（处理 429 rate limit）。"""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=judge_model,
                messages=messages,
                temperature=0.0,
                max_tokens=768,
            )
            return response.choices[0].message.content
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RateLimitExceeded" in err_str or "TPM" in err_str:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Judge rate limited (attempt {attempt+1}/{max_retries}), waiting {delay:.0f}s ...")
                time.sleep(delay)
            else:
                raise
    raise Exception(f"Judge rate limit exceeded after {max_retries} retries")


def run_judge_eval(
    trajectory: List[Dict],
    task_id: str,
    category: str,
    task_prompt: str,
    judge_model: str,
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
    model_name: str = "unknown",
) -> JudgeScore:
    """用 Judge 模型评估单条轨迹"""
    try:
        import openai
    except ImportError:
        logger.error("openai not installed. Run: pip install openai")
        return _error_score(task_id, model_name, "openai not installed")

    if not api_key:
        return _error_score(task_id, model_name, "JUDGE_API_KEY not found")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    trajectory_text = _trajectory_to_text(trajectory)
    prompt = JUDGE_PROMPT.format(
        task_id=task_id,
        category=category,
        task_prompt=task_prompt[:1000],
        trajectory_text=trajectory_text,
    )

    try:
        result_text = _call_judge_with_retry(
            client, judge_model,
            messages=[
                {"role": "system", "content": "You are an expert AI agent evaluator."},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as e:
        logger.error(f"Judge API call failed: {e}")
        return _error_score(task_id, model_name, str(e))

    parsed = _parse_judge_response(result_text)
    if parsed is None:
        logger.warning(f"Failed to parse judge response for {task_id}: {result_text[:200]}")
        return JudgeScore(
            task_id=task_id,
            model=model_name,
            task_completion=0.0,
            tool_usage=0.0,
            reasoning=0.0,
            answer_quality=0.0,
            overall_score=0.0,
            justification=f"Parse error: {result_text[:200]}",
            raw_response=result_text,
        )

    return JudgeScore(
        task_id=task_id,
        model=model_name,
        task_completion=parsed.get("task_completion", 0.0),
        tool_usage=parsed.get("tool_usage", 0.0),
        reasoning=parsed.get("reasoning", 0.0),
        answer_quality=parsed.get("answer_quality", 0.0),
        overall_score=parsed.get("overall_score", 0.0),
        justification=parsed.get("justification", ""),
        raw_response=result_text,
    )


def run_judge_eval_offline(
    trajectory: List[Dict],
    task_id: str,
    category: str,
    task_prompt: str,
    model_name: str,
    judge_model: str,
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
) -> JudgeScore:
    """离线评估已有轨迹（不走 agent.execute）"""
    trajectory_text = _trajectory_to_text(trajectory)
    prompt = JUDGE_PROMPT_OFFLINE.format(
        task_id=task_id,
        category=category,
        task_prompt=task_prompt[:1000],
        model_name=model_name,
        trajectory_text=trajectory_text,
    )

    try:
        import openai
    except ImportError:
        return _error_score(task_id, model_name, "openai not installed")

    if not api_key:
        return _error_score(task_id, model_name, "JUDGE_API_KEY not found")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    try:
        result_text = _call_judge_with_retry(
            client, judge_model,
            messages=[
                {"role": "system", "content": "You are an expert AI agent evaluator."},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as e:
        logger.error(f"Judge API call failed: {e}")
        return _error_score(task_id, model_name, str(e))

    parsed = _parse_judge_response(result_text)
    if parsed is None:
        return JudgeScore(
            task_id=task_id,
            model=model_name,
            task_completion=0.0,
            tool_usage=0.0,
            reasoning=0.0,
            answer_quality=0.0,
            overall_score=0.0,
            justification=f"Parse error: {result_text[:200]}",
            raw_response=result_text,
        )

    return JudgeScore(
        task_id=task_id,
        model=model_name,
        task_completion=parsed.get("task_completion", 0.0),
        tool_usage=parsed.get("tool_usage", 0.0),
        reasoning=parsed.get("reasoning", 0.0),
        answer_quality=parsed.get("answer_quality", 0.0),
        overall_score=parsed.get("overall_score", 0.0),
        justification=parsed.get("justification", ""),
        raw_response=result_text,
    )


def _error_score(task_id: str, model: str, error: str) -> JudgeScore:
    """构建错误评分"""
    return JudgeScore(
        task_id=task_id,
        model=model,
        task_completion=0.0,
        tool_usage=0.0,
        reasoning=0.0,
        answer_quality=0.0,
        overall_score=0.0,
        justification=f"Error: {error}",
    )


def format_judge_score(score: JudgeScore) -> str:
    """格式化评分输出"""
    return (
        f"TC={score.task_completion:.2f} "
        f"TU={score.tool_usage:.2f} "
        f"RE={score.reasoning:.2f} "
        f"AQ={score.answer_quality:.2f} "
        f"OVERALL={score.overall_score:.2f}"
    )
