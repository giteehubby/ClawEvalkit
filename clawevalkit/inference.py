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


def get_harness_config(harness: str) -> dict:
    """Convert harness recipe name to agent constructor kwargs dict.

    Returns a dict like {"memory_config": MemoryConfig(enabled=True)} that
    can be splatted into NanoBotAgent / HarborNanoBotAgent constructors.

    For "procedure" (T4), both T4a and T4b are enabled by default:
      - T4a: Program Support Cards via dense retrieval (BERT bi-encoder)
      - T4b: Skill Activation Prompts (injected at start + re-trigger on unexpected)
    """
    if harness == "memory":
        from OpenClawPro.harness.agent.memory import MemoryConfig
        return {"memory_config": MemoryConfig(enabled=True)}
    elif harness == "control":
        from OpenClawPro.harness.agent.control import (
            ControlConfig,
            PlanFirstConfig,
            ReplanConfig,
            RetryConfig,
            ReflectionConfig,
        )
        # T2: Single-agent control recipe (针对 A/B/D 类失败)
        # - PlanFirst: 任务开始时生成执行计划
        # - Replan: 每 N 步检测重规划信号（每 5 步）
        # - Reflection: 失败后生成诊断
        # - Retry: 工具调用失败重试
        return {
            "control_config": ControlConfig(
                enabled=True,
                plan_first=PlanFirstConfig(
                    enabled=True,
                    trigger="always",
                    max_plan_length=500,
                ),
                replan=ReplanConfig(
                    enabled=True,
                    signal_threshold=5,
                    signals=["error", "repeated_action"],
                    max_replans=2,
                    min_iterations_between_replans=2,
                ),
                retry=RetryConfig(
                    enabled=True,
                    max_retries=2,
                    backoff="exponential",
                    base_delay=1.0,
                    retryable_errors=["rate_limit", "timeout", "transient"],
                    fatal_errors=["invalid_params", "auth_failed", "permission_denied"],
                ),
                reflection=ReflectionConfig(
                    enabled=True,
                    trigger="on_failure",
                    consecutive_failure_threshold=2,
                    max_reflection_length=300,
                ),
                preflight_enabled=False,  # T2(b) 前置检查，可选开启
            )
        }
    elif harness == "collaboration":
        from OpenClawPro.harness.agent.collaboration import CollabConfig
        return {"collab_config": CollabConfig(enabled=True)}
    elif harness == "procedure":
        from OpenClawPro.harness.agent.procedure import (
            ProceduralConfig,
            ProgramSupportConfig,
            RetrievalConfig,
            SkillActivationConfig,
        )
        import os
        # Default cards directory: OpenClawPro/harness/agent/procedure/cards
        repo_root = Path(__file__).parent.parent
        default_cards_dir = str(repo_root / "OpenClawPro" / "harness" / "agent" / "procedure" / "cards")

        program_support = ProgramSupportConfig(
            enabled=True,
            cards_dir=os.environ.get("T4A_CARDS_DIR", default_cards_dir),
            retrieval=RetrievalConfig(
                embedding_model=os.environ.get("T4A_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
                device=os.environ.get("T4A_DEVICE", "cpu"),
                top_k=int(os.environ.get("T4A_TOP_K", "3")),
                batch_size=16,
                cache_embeddings=True,
            ),
            use_keyword_fallback=True,
        )

        skill_activation = SkillActivationConfig(
            enabled=True,
            inject_at_start=True,
            retrigger_on_unexpected=True,
            unexpected_threshold=1,
            include_inventory=True,
            include_selection=True,
            include_verification=True,
        )

        return {
            "procedural_config": ProceduralConfig(
                enabled=True,
                program_support=program_support,
                skill_activation=skill_activation,
            )
        }
    return {}


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
    reuse_container = kwargs.pop("reuse_container", False)
    if bench_key == "skillsbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else True,
                     reuse_container=reuse_container)
    elif bench_key == "wildclawbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "agentbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "clawbench-official":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "zclawbench":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "tribe":
        bench = bcls(use_docker=use_docker if use_docker is not None else False)
    elif bench_key == "claweval":
        bench = bcls()
    else:
        bench = bcls()
    if output_dir:
        bench.output_dir = Path(output_dir)

    config = get_model_config(model_key)
    force = kwargs.get("force", False)

    # Skip benchmark-level cache check when sample is specified
    # (individual task caching is handled inside benchmark.evaluate)
    if not force and not sample:
        cached = bench.collect(model_key)
        if cached and cached.get("score") is not None and cached.get("pending", 1) == 0:
            log(f"  [{bench_key}×{model_key}] cached: score={cached['score']}")
            return cached

    log(f"  [{bench_key}×{model_key}] evaluating...")
    # 传递task_ids和category参数
    evaluate_kwargs = {"sample": sample, "use_docker": use_docker}
    # 传递 transcripts_dir（如果提供）
    transcripts_dir = kwargs.pop("transcripts_dir", None)
    if transcripts_dir:
        evaluate_kwargs["transcripts_dir"] = transcripts_dir
    if "task_ids" in kwargs:
        evaluate_kwargs["task_ids"] = kwargs.pop("task_ids")
    if "category" in kwargs:
        evaluate_kwargs["category"] = kwargs.pop("category")
    # 提取 harness 并转化为 agent config kwargs
    harness = kwargs.pop("harness", None)
    if harness:
        evaluate_kwargs["harness_config"] = get_harness_config(harness)
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
        # Use instance task_count if available (for dynamic task counts like zclawbench)
        bcls = BENCHMARKS[bkey]
        use_docker = kwargs.get("use_docker", None)
        if bkey == "zclawbench":
            temp_bench = bcls(use_docker=use_docker if use_docker is not None else False)
            task_count = temp_bench.task_count
        else:
            task_count = bcls.TASK_COUNT
        log(f"BENCHMARK: {bcls.DISPLAY_NAME} ({task_count} tasks)")
        log(f"{'=' * 60}")

        for mkey in model_keys:
            result = infer_data_job(bkey, mkey, sample=sample,
                                   output_dir=output_dir, **kwargs)
            results[(bkey, mkey)] = result

    return results
