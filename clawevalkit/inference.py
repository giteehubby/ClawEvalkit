"""Inference dispatcher — runs benchmark × model evaluation jobs.

Mirrors vlmeval/inference.py pattern: each job is one (benchmark, model) pair.
Handles result caching (skip if already evaluated) and error reporting.
"""
from pathlib import Path

from .config import get_model_config, MODELS, load_env
from .dataset import BENCHMARKS
from .utils.log import log

# Auto-load .env file on module import
load_env()


def infer_data_job(bench_key: str, model_key: str, sample: int = 0,
                   output_dir: Path = None, **kwargs) -> dict:
    """Run a single benchmark × model evaluation job.

    整体流程:
    1. 查找 benchmark 类和模型配置
    2. 检查是否已有缓存结果（可通过 force=True 强制重跑）
    3. 调用 benchmark.evaluate() 执行评测
    4. 返回结果 dict

    Args:
        bench_key: benchmark 注册名 (如 "tribe", "zclawbench")
        model_key: 模型注册名 (如 "claude-sonnet", "gpt-4.1")
        sample: 采样任务数 (0=全量)
        output_dir: 结果输出目录 (默认 ./outputs/)
        **kwargs: force=True 强制重跑, max_turns=N, task_ids=[], category= 等传给 benchmark

    Returns:
        {"score": float, "passed": int, "total": int, ...}
    """
    if bench_key not in BENCHMARKS:
        return {"score": 0, "total": 0, "error": f"Unknown benchmark: {bench_key}"}
    if model_key not in MODELS:
        return {"score": 0, "total": 0, "error": f"Unknown model: {model_key}"}

    bcls = BENCHMARKS[bench_key]
    # Pass use_docker to benchmarks that support it via constructor
    use_docker = kwargs.pop("use_docker", None)
    if bench_key == "skillsbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else True)
    elif bench_key == "wildclawbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "agentbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "pinchbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    else:
        bench = bcls()
    if output_dir:
        bench.output_dir = Path(output_dir)

    config = get_model_config(model_key)
    force = kwargs.get("force", False)

    # 检查缓存
    if not force:
        cached = bench.collect(model_key)
        if cached and cached.get("score") is not None:
            log(f"  [{bench_key}×{model_key}] cached: score={cached['score']}")
            return cached

    log(f"  [{bench_key}×{model_key}] evaluating...")
    # 传递task_ids和category参数
    evaluate_kwargs = {"sample": sample}
    if "task_ids" in kwargs:
        evaluate_kwargs["task_ids"] = kwargs.pop("task_ids")
    if "category" in kwargs:
        evaluate_kwargs["category"] = kwargs.pop("category")
    result = bench.evaluate(model_key, config, **evaluate_kwargs, **kwargs)

    score = result.get("score", 0)
    total = result.get("total", 0)
    scored = result.get("scored", result.get("passed", 0))  #兼容新旧字段
    log(f"  [{bench_key}×{model_key}] done: score={score}, scored={scored}/{total}")

    if result.get("error"):
        log(f"  [{bench_key}×{model_key}] error: {result['error'][:200]}")

    return result


def infer_all(bench_keys: list = None, model_keys: list = None,
              sample: int = 0, output_dir: Path = None, **kwargs) -> dict:
    """Run all benchmark × model combinations.

    Args:
        bench_keys: 要评测的 benchmark 列表 (None=全部)
        model_keys: 要评测的模型列表 (None=["claude-sonnet"])
        sample: 采样任务数
        output_dir: 结果输出目录
        **kwargs: 传给 infer_data_job

    Returns:
        {(bench_key, model_key): result_dict, ...}
    """
    bench_keys = bench_keys or list(BENCHMARKS.keys())
    model_keys = model_keys or ["claude-sonnet"]

    results = {}
    for bkey in bench_keys:
        log(f"\n{'=' * 60}")
        log(f"BENCHMARK: {BENCHMARKS[bkey].DISPLAY_NAME} ({BENCHMARKS[bkey].TASK_COUNT} tasks)")
        log(f"{'=' * 60}")

        for mkey in model_keys:
            result = infer_data_job(bkey, mkey, sample=sample,
                                   output_dir=output_dir, **kwargs)
            results[(bkey, mkey)] = result

    return results
