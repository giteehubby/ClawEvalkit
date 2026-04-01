"""Example: How to add a custom benchmark to ClawEvalKit.

To add your own benchmark:
1. Create a class inheriting from BaseBenchmark
2. Implement evaluate() and optionally collect()
3. Register in clawevalkit/dataset/__init__.py
"""
from clawevalkit.dataset.base import BaseBenchmark
from clawevalkit.utils.api import call_llm


class MyCustomBench(BaseBenchmark):
    DISPLAY_NAME = "My Custom Benchmark"
    TASK_COUNT = 3
    SCORE_RANGE = "0-100"

    TASKS = [
        {"id": "math", "prompt": "What is 2+2?", "answer": "4"},
        {"id": "capital", "prompt": "Capital of France?", "answer": "Paris"},
        {"id": "color", "prompt": "What color is the sky?", "answer": "blue"},
    ]

    def evaluate(self, model_key, config, sample=0, **kwargs):
        passed = 0
        for task in self.TASKS:
            response = call_llm(
                [{"role": "user", "content": task["prompt"]}],
                config, max_tokens=100,
            )
            if task["answer"].lower() in response.lower():
                passed += 1

        score = round(passed / len(self.TASKS) * 100, 1)
        result = {"score": score, "passed": passed, "total": len(self.TASKS)}
        self.save_result("custom", model_key, result)
        return result


# To register: add to clawevalkit/dataset/__init__.py:
# from .custom import MyCustomBench
# BENCHMARKS["custom"] = MyCustomBench
