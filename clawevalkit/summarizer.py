"""Result summarizer — collects and displays evaluation results.

Mirrors vlmeval's summary pattern: scan results directory, aggregate scores,
and output as terminal table or markdown.
"""
from .config import MODELS
from .dataset import BENCHMARKS


# 短名映射
SHORT_NAMES = {
    "zclawbench": "ZClaw", "wildclawbench": "WildClaw", "clawbench-official": "ClawOff",
    "pinchbench": "Pinch", "agentbench": "Agent", "skillbench": "Skill",
    "skillsbench": "Skills", "tribe": "Tribe",
    "claweval": "ClawEval",
}


class Summarizer:
    """Collect and display evaluation results across benchmarks and models.

    使用方式:
        summarizer = Summarizer()
        summarizer.summary()           # 终端表格
        md = summarizer.to_markdown()   # Markdown 表格
    """

    def __init__(self, output_dir=None):
        from pathlib import Path
        self.output_dir = Path(output_dir) if output_dir and not isinstance(output_dir, Path) else output_dir

    def collect_all(self) -> tuple:
        """收集所有 bench × model 的已有结果。

        Returns:
            (table, all_models) where:
            - table: {bench_key: {model_key: score}}
            - all_models: sorted list of model keys with results
        """
        all_models = set()
        table = {}

        for bkey, bcls in BENCHMARKS.items():
            bench = bcls()
            if self.output_dir:
                bench.output_dir = self.output_dir
            bench_scores = {}
            for mkey in MODELS:
                result = bench.collect(mkey)
                if result and result.get("score") is not None:
                    bench_scores[mkey] = result["score"]
                    all_models.add(mkey)
            if bench_scores:
                table[bkey] = bench_scores

        return table, sorted(all_models)

    def summary(self):
        """打印终端汇总表格（已禁用，仅保留日志输出）。"""
        table, all_models = self.collect_all()

        if not table:
            print("No results found. Run evaluation first.")
            return

        # 汇总表格已禁用，如需启用请参考 to_markdown() 方法
        pass

    def to_markdown(self) -> str:
        """生成 Markdown 格式的汇总表格。"""
        table, all_models = self.collect_all()
        if not table:
            return "No results found."

        bench_keys = [k for k in BENCHMARKS if k in table]
        header = "| Model | " + " | ".join(SHORT_NAMES.get(b, b) for b in bench_keys) + " |"
        separator = "|---|" + "|".join("---:" for _ in bench_keys) + "|"
        rows = [header, separator]

        for model in all_models:
            name = MODELS.get(model, {}).get("name", model)
            cells = [name]
            for bkey in bench_keys:
                score = table.get(bkey, {}).get(model)
                if score is not None:
                    fmt = f"{score:.3f}" if BENCHMARKS[bkey].SCORE_RANGE == "0-1" else f"{score:.1f}"
                    cells.append(fmt)
                else:
                    cells.append("—")
            rows.append("| " + " | ".join(cells) + " |")

        return "\n".join(rows)
