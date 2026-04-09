"""
ClawEvalKit Grading — 评分逻辑模块。

包含各 benchmark 的 judge 评分、自动评分等评测逻辑。
"""
from .zclawbench_grading import JudgeScore, run_judge_eval, run_judge_eval_offline, format_judge_score
from .wildclawbench_grading import run_automated_checks, run_grading
from .judge_prompt import JUDGE_PROMPT, JUDGE_PROMPT_OFFLINE

__all__ = [
    "JudgeScore",
    "run_judge_eval",
    "run_judge_eval_offline",
    "format_judge_score",
    "run_automated_checks",
    "run_grading",
    "JUDGE_PROMPT",
    "JUDGE_PROMPT_OFFLINE",
]
