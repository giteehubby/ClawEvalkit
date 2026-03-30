"""
ZClawBench Judge 评分逻辑。

使用 Judge Model (doubao-seed-1.8) 对轨迹进行评估，
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

from src.runners.adapters.zclawbench.judge_prompt import JUDGE_PROMPT, JUDGE_PROMPT_OFFLINE

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


def get_ark_key(baserunners_dir: Path) -> str:
    """从环境或配置文件读取 ARK API Key

    baserunners_dir = nanopro/src/runners
    需要往上级找到 Agent-Factory-Med/0001_utils/api/.env
    """
    # nanopro/src/runners 往上 6 层 = Agent-Factory-Med/
    env_file = baserunners_dir.parent.parent.parent.parent.parent.parent / "0001_utils" / "api" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ARK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("ARK_API_KEY", "")


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


def run_judge_eval(
    trajectory: List[Dict],
    task_id: str,
    category: str,
    task_prompt: str,
    judge_model: str,
    api_key: str,
    base_url: str = "https://ark-cn-beijing.bytedance.net/api/v3",
    model_name: str = "unknown",
) -> JudgeScore:
    """用 Judge 模型评估单条轨迹"""
    try:
        import openai
    except ImportError:
        logger.error("openai not installed. Run: pip install openai")
        return _error_score(task_id, model_name, "openai not installed")

    if not api_key:
        return _error_score(task_id, model_name, "ARK_API_KEY not found")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    trajectory_text = _trajectory_to_text(trajectory)
    prompt = JUDGE_PROMPT.format(
        task_id=task_id,
        category=category,
        task_prompt=task_prompt[:1000],
        trajectory_text=trajectory_text,
    )

    try:
        response = client.chat.completions.create(
            model=judge_model,
            messages=[
                {"role": "system", "content": "You are an expert AI agent evaluator."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=768,
        )
        result_text = response.choices[0].message.content
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
    base_url: str = "https://ark-cn-beijing.bytedance.net/api/v3",
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
        return _error_score(task_id, model_name, "ARK_API_KEY not found")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    try:
        response = client.chat.completions.create(
            model=judge_model,
            messages=[
                {"role": "system", "content": "You are an expert AI agent evaluator."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=768,
        )
        result_text = response.choices[0].message.content
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
