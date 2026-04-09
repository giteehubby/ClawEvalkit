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
    """从 Judge 模型响应中解析 JSON 评分（通过括号匹配）"""
    # 去掉 markdown code block 包裹 (```json ... ``` 或 ``` ... ```)
    stripped = response_text.strip()
    if stripped.startswith("```"):
        # 去掉开头 ```json 或 ```
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        # 去掉结尾 ```
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()

    # 尝试整段解析
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 通过括号匹配提取 JSON
    start = response_text.find('{')
    if start == -1:
        return None

    depth = 0
    end = start
    for i, c in enumerate(response_text[start:], start):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth == 0 and end > start:
        try:
            return json.loads(response_text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _call_judge_with_retry(
    client,
    judge_model: str,
    messages: List[Dict],
    max_retries: int = 5,
    base_delay: float = 5.0,
    timeout: float = 120.0,
    client_type: str = "openai",
) -> Optional[str]:
    """调用 Judge 模型，带指数退避重试（处理 429 rate limit）。

    Args:
        client: OpenAI 或 Anthropic 客户端
        judge_model: Judge 模型名称
        messages: 消息列表
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        timeout: 超时时间（秒）
        client_type: "openai" 或 "anthropic"
    """
    for attempt in range(max_retries):
        try:
            if client_type == "anthropic":
                response = client.messages.create(
                    model=judge_model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=768,
                    timeout=timeout,
                )
                # Handle both text and thinking blocks (MiniMax returns thinking by default)
                for block in response.content:
                    if block.type == "text":
                        return block.text
                # If no text block found, use thinking block content
                if response.content and response.content[0].type == "thinking":
                    return response.content[0].thinking
                return None
            else:
                response = client.chat.completions.create(
                    model=judge_model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=768,
                    timeout=timeout,
                )
                return response.choices[0].message.content
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RateLimitExceeded" in err_str or "TPM" in err_str:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Judge rate limited (attempt {attempt+1}/{max_retries}), waiting {delay:.0f}s ...")
                time.sleep(delay)
            elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
                logger.warning(f"Judge API timeout (attempt {attempt+1}/{max_retries}): {err_str}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise
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
    """用 Judge 模型评估单条轨迹

    Args:
        trajectory: Agent 轨迹
        task_id: 任务 ID
        category: 任务类别
        task_prompt: 任务提示
        judge_model: Judge 模型名（如 "anthropic/claude-sonnet-4-20250514" 或 "minimax/claude-3.5-sonnet")
        api_key: API Key
        base_url: API 基础 URL
        model_name: 被评估的模型名
    """
    # 检测是否使用 Anthropic 兼容 API（MiniMax 或原生 Anthropic）
    use_anthropic = judge_model.startswith("anthropic/") or "minimax" in base_url.lower()

    if use_anthropic:
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic not installed. Run: pip install anthropic")
            return _error_score(task_id, model_name, "anthropic not installed")

        if not api_key:
            return _error_score(task_id, model_name, "API key not found")

        client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        client_type = "anthropic"
    else:
        try:
            import openai
        except ImportError:
            logger.error("openai not installed. Run: pip install openai")
            return _error_score(task_id, model_name, "openai not installed")

        if not api_key:
            return _error_score(task_id, model_name, "JUDGE_API_KEY not found")

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        client_type = "openai"

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
                {"role": "user", "content": f"You are an expert AI agent evaluator.\n\n{prompt}"},
            ],
            client_type=client_type,
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

    # 检测是否使用 Anthropic 兼容 API（MiniMax 或原生 Anthropic）
    use_anthropic = judge_model.startswith("anthropic/") or "minimax" in base_url.lower()

    if use_anthropic:
        try:
            import anthropic
        except ImportError:
            return _error_score(task_id, model_name, "anthropic not installed")

        if not api_key:
            return _error_score(task_id, model_name, "API key not found")

        client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        client_type = "anthropic"
    else:
        try:
            import openai
        except ImportError:
            return _error_score(task_id, model_name, "openai not installed")

        if not api_key:
            return _error_score(task_id, model_name, "JUDGE_API_KEY not found")

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        client_type = "openai"

    try:
        result_text = _call_judge_with_retry(
            client, judge_model,
            messages=[
                {"role": "user", "content": f"You are an expert AI agent evaluator.\n\n{prompt}"},
            ],
            client_type=client_type,
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
