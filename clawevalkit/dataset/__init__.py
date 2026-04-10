"""Dataset (Benchmark) registry — one file per benchmark, auto-discovered by run.py.

Each benchmark inherits BaseBenchmark and implements evaluate() + collect().
Register new benchmarks by adding to the BENCHMARKS dict below.
"""
from .base import BaseBenchmark
from .zclawbench import ZClawBench
from .wildclawbench import WildClawBench
from .clawbench_official import ClawBenchOfficial
from .pinchbench import PinchBench
from .agentbench import AgentBench
from .skillbench import SkillBench
from .skillsbench import SkillsBench
from .tribe import TribeBench
from .claweval import ClawEval

# benchmark_key → class 映射
BENCHMARKS = {
    "zclawbench": ZClawBench,
    "wildclawbench": WildClawBench,
    "clawbench-official": ClawBenchOfficial,
    "pinchbench": PinchBench,
    "agentbench": AgentBench,
    "skillbench": SkillBench,
    "skillsbench": SkillsBench,
    "tribe": TribeBench,
    "claweval": ClawEval,
}


def list_benchmarks() -> list:
    """返回 [(key, display_name, task_count)] 列表。"""
    return [(k, cls.DISPLAY_NAME, cls.TASK_COUNT) for k, cls in BENCHMARKS.items()]
