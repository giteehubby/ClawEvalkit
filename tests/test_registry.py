"""Test benchmark and model registries."""
from clawevalkit.dataset import BENCHMARKS, list_benchmarks
from clawevalkit.dataset.base import BaseBenchmark
from clawevalkit.api import PROVIDERS, get_model
from clawevalkit.api.base import BaseAPI


def test_benchmarks_registered():
    assert len(BENCHMARKS) == 8
    expected = {"zclawbench", "wildclawbench", "clawbench-official", "pinchbench",
                "agentbench", "skillbench", "skillsbench", "tribe"}
    assert set(BENCHMARKS.keys()) == expected


def test_benchmark_classes():
    for key, cls in BENCHMARKS.items():
        assert issubclass(cls, BaseBenchmark), f"{key} not a BaseBenchmark subclass"
        inst = cls()
        assert inst.DISPLAY_NAME, f"{key} missing DISPLAY_NAME"
        assert inst.TASK_COUNT > 0, f"{key} has TASK_COUNT=0"


def test_list_benchmarks():
    benchmarks = list_benchmarks()
    assert len(benchmarks) == 8
    keys = [b[0] for b in benchmarks]
    assert "tribe" in keys


def test_providers_registered():
    assert "ark" in PROVIDERS
    assert "openrouter" in PROVIDERS
    assert "gpt_proxy" in PROVIDERS


def test_api_classes():
    for name, cls in PROVIDERS.items():
        assert issubclass(cls, BaseAPI), f"{name} not a BaseAPI subclass"
