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
}


class Summarizer:
    """Collect and display evaluation results across benchmarks and models.

    使用方式:
        summarizer = Summarizer()
        summarizer.summary()           # 终端表格
        md = summarizer.to_markdown()   # Markdown 表格
    """

    def __init__(self, output_dir=None):
        self.output_dir = output_dir

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
        """打印终端汇总表格。"""
        table, all_models = self.collect_all()

        if not table:
            print("No results found. Run evaluation first.")
            return

        bench_keys = [k for k in BENCHMARKS if k in table]
        col_width = 10
        name_width = 22
        total_width = name_width + col_width * len(bench_keys)

        header = f"{'Model':>{name_width}s}" + "".join(
            f"{SHORT_NAMES.get(b, b):>{col_width}s}" for b in bench_keys
        )

        print(f"\n{'=' * total_width}")
        print("  CLAWEVALKIT EVALUATION SUMMARY")
        print(f"{'=' * total_width}")
        print(header)
        print("-" * total_width)

        for model in all_models:
            name = MODELS.get(model, {}).get("name", model)
            row = f"{name:>{name_width}s}"
            for bkey in bench_keys:
                score = table.get(bkey, {}).get(model)
                if score is not None:
                    fmt = f"{score:>{col_width}.3f}" if BENCHMARKS[bkey].SCORE_RANGE == "0-1" else f"{score:>{col_width}.1f}"
                    row += fmt
                else:
                    row += f"{'—':>{col_width}s}"
            print(row)

        print(f"{'=' * total_width}\n")

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
