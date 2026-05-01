"""
统计 outputs 目录下各 benchmark 的任务完成情况与平均分数，并用 matplotlib 可视化。

用法: python scripts/visualize_outputs_summary.py
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams["font.sans-serif"] = [
    "Arial Unicode MS", "PingFang SC", "SimHei", "DejaVu Sans"
]
matplotlib.rcParams["axes.unicode_minus"] = False

PROJECT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT / "outputs"
BENCHMARKS_DIR = PROJECT / "benchmarks"
MODEL = "glm-4.7"

# benchmark 名称映射: outputs 中的名 -> benchmarks 中的名
BENCH_NAME_MAP = {
    "agentbench": "agentbench-openclaw",
    "claweval": "claw-eval",
    "clawbench-official": "claw-bench",
    # tribe 已废弃
    "pinchbench": "pinchbench",
    "skillsbench": "skillsbench",
    # wildclawbench 已废弃
    "zclawbench": "zclawbench",
}

DISPLAY_NAMES = {
    "agentbench": "AgentBench",
    "claweval": "ClawEval",
    "clawbench-official": "ClawBench",
    # tribe 已废弃
    "pinchbench": "PinchBench",
    "skillsbench": "SkillsBench",
    # wildclawbench 已废弃
    "zclawbench": "ZClawBench",
}

# harness 颜色
HARNESS_COLORS = {
    "control": "#4CAF50",
    "collaboration": "#2196F3",
    "memory": "#FF9800",
    "procedure": "#E91E63",
}
BASELINE_COLOR = "#4fc3f7"


# ── 工具函数 ──────────────────────────────────────────────


def count_total_tasks(bench_key: str) -> int:
    """从 benchmarks 目录统计总任务数（支持单层和双层 tasks 目录）"""
    bench_dir = BENCHMARKS_DIR / BENCH_NAME_MAP.get(bench_key, bench_key)
    if not bench_dir.exists():
        return 0
    tasks_dir = bench_dir / "tasks"
    if tasks_dir.exists():
        dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))]
        if not dirs:
            return 0
        # 判断是单层还是双层：如果子目录里还有子目录，说明是 category/task 两级结构
        has_sub_tasks = any(
            any(c.is_dir() for c in d.iterdir()) for d in dirs if d.is_dir()
        )
        if has_sub_tasks:
            return sum(
                len([c for c in d.iterdir() if c.is_dir()])
                for d in dirs
            )
        return len(dirs)
    tasks_json = bench_dir / "tasks.json"
    if tasks_json.exists():
        data = json.loads(tasks_json.read_text())
        if isinstance(data, dict) and "tasks" in data:
            return len(data["tasks"])
        if isinstance(data, list):
            return len(data)
    return 0


def extract_score(data: dict) -> float:
    """从不同格式的 result dict 中提取 overall score，统一到 0~100"""
    # AgentBench 风格: scores.overall_score (已是 0~100)
    if "scores" in data and isinstance(data["scores"], dict):
        os_ = data["scores"].get("overall_score")
        if os_ is not None:
            return os_
    # ClawEval / ClawBench 风格: score (0~1 或 0~100)
    if "score" in data:
        s = data["score"]
        return s * 100 if s <= 1 else s
    # PinchBench 风格: mean (0~1)
    if "mean" in data:
        m = data["mean"]
        return m * 100 if m <= 1 else m
    # SkillsBench 风格: status=passed -> 100, 否则 0
    if "status" in data and data["status"] in ("passed", "success", "failed", "error"):
        return 100.0 if data["status"] in ("passed", "success") else 0.0
    return 0.0


def scan_benchmark(bench_dir: Path) -> dict:
    """扫描一个 bench 目录下所有 task 的 result.json"""
    model_dir = bench_dir / MODEL
    if not model_dir.exists():
        return {"tasks_run": 0, "scores": [], "avg": 0.0}

    # 判断目录结构: task 目录 vs 直接 json 文件
    scores = []
    for item in sorted(model_dir.iterdir()):
        data = None
        if item.is_dir():
            rf = item / "result.json"
            if rf.exists():
                try:
                    data = json.loads(rf.read_text())
                except json.JSONDecodeError:
                    pass
        elif item.suffix == ".json":
            try:
                data = json.loads(item.read_text())
            except json.JSONDecodeError:
                pass
        if data:
            scores.append(extract_score(data))

    avg = round(sum(scores) / len(scores), 2) if scores else 0.0
    return {"tasks_run": len(scores), "scores": scores, "avg": avg}


def collect_all_data() -> dict:
    """收集 baseline + 各 harness 数据"""
    baseline = {}
    for bench_dir in sorted(OUTPUTS_DIR.iterdir()):
        if not bench_dir.is_dir() or bench_dir.name in ("harness",):
            continue
        bk = bench_dir.name
        if bk not in BENCH_NAME_MAP:
            continue
        total = count_total_tasks(bk)
        stats = scan_benchmark(bench_dir)
        # 取 benchmarks 和 outputs 中较大值（agentbench 等可能跑超集）
        total = max(total, stats["tasks_run"])
        baseline[bk] = {**stats, "total": total}

    harness = {}
    h_dir = OUTPUTS_DIR / "harness"
    if h_dir.exists():
        for ht_dir in sorted(h_dir.iterdir()):
            if not ht_dir.is_dir():
                continue
            ht = ht_dir.name
            harness[ht] = {}
            for bench_dir in sorted(ht_dir.iterdir()):
                if not bench_dir.is_dir():
                    continue
                bk = bench_dir.name
                if bk not in BENCH_NAME_MAP:
                    continue
                # total 从 baseline 取（已处理过 max）
                total = baseline.get(bk, {}).get("total", count_total_tasks(bk))
                stats = scan_benchmark(bench_dir)
                harness[ht][bk] = {**stats, "total": total}

    return {"baseline": baseline, "harness": harness}


# ── 可视化 ────────────────────────────────────────────────


def visualize(data: dict):
    """用 matplotlib 画 2x1 子图: 完成率 + 平均分"""
    bench_keys = [k for k in BENCH_NAME_MAP
                  if any(k in data["baseline"] or k in v for v in data["harness"].values())]
    bench_keys = [k for k in BENCH_NAME_MAP if k in bench_keys]  # 保持顺序
    # 过滤: 至少有一个来源有数据
    bench_keys = [k for k in bench_keys
                  if data["baseline"].get(k, {}).get("tasks_run", 0) > 0
                  or any(data["harness"].get(ht, {}).get(k, {}).get("tasks_run", 0) > 0
                         for ht in data["harness"])]
    harness_types = sorted(data["harness"].keys())
    labels = [DISPLAY_NAMES.get(k, k) for k in bench_keys]
    n = len(labels)
    x = np.arange(n)
    bar_w = 0.8 / (1 + len(harness_types))  # 总 bar 组宽度分配

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(max(14, n * 2), 10), facecolor="#1a1a2e")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("#555")
        ax.spines["left"].set_color("#555")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")

    # ── 图1: 完成率 ──
    offsets = np.arange(-(len(harness_types)) / 2, (len(harness_types)) / 2 + 1)
    idx = 0
    # baseline
    bl_rates = []
    for bk in bench_keys:
        bl = data["baseline"].get(bk, {"tasks_run": 0, "total": 0})
        rate = bl["tasks_run"] / bl["total"] * 100 if bl["total"] > 0 else 0
        bl_rates.append(rate)
    ax1.bar(x + offsets[idx] * bar_w, bl_rates, bar_w * 0.9, label="Baseline",
            color=BASELINE_COLOR, edgecolor="white", linewidth=0.3)
    idx += 1
    # harness
    for ht in harness_types:
        ht_rates = []
        for bk in bench_keys:
            hd = data["harness"].get(ht, {}).get(bk, {"tasks_run": 0, "total": 0})
            rate = hd["tasks_run"] / hd["total"] * 100 if hd["total"] > 0 else 0
            ht_rates.append(rate)
        color = HARNESS_COLORS.get(ht, "#9C27B0")
        ax1.bar(x + offsets[idx] * bar_w, ht_rates, bar_w * 0.9,
                label=ht.capitalize(), color=color, edgecolor="white", linewidth=0.3)
        idx += 1

    ax1.set_ylabel("Completion Rate (%)", fontsize=11)
    ax1.set_title("Task Completion Rate by Benchmark", fontsize=13, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax1.set_ylim(0, 115)
    ax1.legend(fontsize=8, loc="upper right", facecolor="#1a1a2e", edgecolor="#555",
               labelcolor="white")
    # 在柱子上方标注 实际值
    for bars_obj in ax1.containers:
        ax1.bar_label(bars_obj, fmt="%.0f%%", fontsize=7, color="white", padding=2)

    # ── 图2: 平均分 ──
    idx = 0
    bl_avgs = [data["baseline"].get(bk, {"avg": 0})["avg"] for bk in bench_keys]
    ax2.bar(x + offsets[idx] * bar_w, bl_avgs, bar_w * 0.9, label="Baseline",
            color=BASELINE_COLOR, edgecolor="white", linewidth=0.3)
    idx += 1
    for ht in harness_types:
        ht_avgs = [data["harness"].get(ht, {}).get(bk, {"avg": 0})["avg"] for bk in bench_keys]
        color = HARNESS_COLORS.get(ht, "#9C27B0")
        ax2.bar(x + offsets[idx] * bar_w, ht_avgs, bar_w * 0.9,
                label=ht.capitalize(), color=color, edgecolor="white", linewidth=0.3)
        idx += 1

    ax2.set_ylabel("Average Score", fontsize=11)
    ax2.set_title("Average Overall Score by Benchmark", fontsize=13, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax2.set_ylim(0, 115)
    ax2.legend(fontsize=8, loc="upper right", facecolor="#1a1a2e", edgecolor="#555",
               labelcolor="white")
    for bars_obj in ax2.containers:
        ax2.bar_label(bars_obj, fmt="%.1f", fontsize=7, color="white", padding=2)

    fig.suptitle(f"Outputs 实验统计总览  (Model: {MODEL})", fontsize=15,
                 fontweight="bold", color="white", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    output_path = OUTPUTS_DIR / "outputs_summary.png"
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print(f"\n可视化已保存: {output_path}")


# ── main ──────────────────────────────────────────────────


def save_markdown(data: dict, output_path: Path):
    """将统计数据保存为 Markdown 表格"""
    harness_types = sorted(data["harness"].keys())

    lines = [
        f"# Outputs 实验统计总览 (Model: {MODEL})",
        "",
        "## Average Score",
        "",
        f"| Benchmark | Total | BL Avg | " + " | ".join(ht.capitalize() + " Avg" for ht in harness_types) + " |",
        f"| --- | ---: | ---: |" + " ---: |" * len(harness_types),
    ]

    for bk in BENCH_NAME_MAP:
        bl = data["baseline"].get(bk, {"tasks_run": 0, "total": 0, "avg": 0})
        name = DISPLAY_NAMES.get(bk, bk)
        if bk not in data["baseline"] and not any(bk in data["harness"].get(ht, {}) for ht in harness_types):
            continue
        row = f"| {name} | {bl['total']} | {bl['avg']:.1f} |"
        for ht in harness_types:
            hd = data["harness"].get(ht, {}).get(bk, {"tasks_run": 0, "avg": 0})
            row += f" {hd['avg']:.1f} |"
        lines.append(row)

    lines += [
        "",
        "## Completion Rate (%)",
        "",
        f"| Benchmark | Total | BL | " + " | ".join(ht.capitalize() for ht in harness_types) + " |",
        f"| --- | ---: | ---: |" + " ---: |" * len(harness_types),
    ]

    for bk in BENCH_NAME_MAP:
        bl = data["baseline"].get(bk, {"tasks_run": 0, "total": 0})
        if bk not in data["baseline"] and not any(bk in data["harness"].get(ht, {}) for ht in harness_types):
            continue
        name = DISPLAY_NAMES.get(bk, bk)
        total = bl["total"]
        bl_rate = bl["tasks_run"] / total * 100 if total > 0 else 0
        row = f"| {name} | {total} | {bl_rate:.1f}% |"
        for ht in harness_types:
            hd = data["harness"].get(ht, {}).get(bk, {"tasks_run": 0, "total": 0})
            ht_total = hd.get("total", total)
            ht_rate = hd["tasks_run"] / ht_total * 100 if ht_total > 0 else 0
            row += f" {ht_rate:.1f}% |"
        lines.append(row)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Markdown 已保存: {output_path}")


def main():
    print("正在收集数据...")
    data = collect_all_data()

    # 打印表格摘要
    harness_types = sorted(data["harness"].keys())
    header = f"{'Benchmark':<20} {'Total':>6} {'BL#':>5} {'BL↑':>6} |"
    for ht in harness_types:
        header += f" {ht[:4]:>5}↑ |"
    print(f"\n{header}")
    print("-" * len(header))

    for bk in BENCH_NAME_MAP:
        bl = data["baseline"].get(bk, {"tasks_run": 0, "total": 0, "avg": 0})
        name = DISPLAY_NAMES.get(bk, bk)
        line = f"{name:<20} {bl['total']:>6} {bl['tasks_run']:>5} {bl['avg']:>6.1f} |"
        for ht in harness_types:
            hd = data["harness"].get(ht, {}).get(bk, {"tasks_run": 0, "avg": 0})
            line += f" {hd['avg']:>6.1f} |"
        print(line)

    # 打印完成率表格
    print(f"\n{'='*len(header)}")
    header2 = f"{'Benchmark':<20} {'Total':>6} {'BL':>6} |"
    for ht in harness_types:
        header2 += f" {ht[:4]:>6} |"
    print(header2)
    print("-" * len(header2))

    for bk in BENCH_NAME_MAP:
        bl = data["baseline"].get(bk, {"tasks_run": 0, "total": 0})
        if bk not in data["baseline"] and not any(bk in data["harness"].get(ht, {}) for ht in harness_types):
            continue
        name = DISPLAY_NAMES.get(bk, bk)
        total = bl["total"]
        bl_rate = bl["tasks_run"] / total * 100 if total > 0 else 0
        line = f"{name:<20} {total:>6} {bl_rate:>5.1f}% |"
        for ht in harness_types:
            hd = data["harness"].get(ht, {}).get(bk, {"tasks_run": 0, "total": 0})
            ht_total = hd.get("total", total)
            ht_rate = hd["tasks_run"] / ht_total * 100 if ht_total > 0 else 0
            line += f" {ht_rate:>5.1f}% |"
        print(line)

    visualize(data)
    save_markdown(data, OUTPUTS_DIR / "outputs_summary.md")


if __name__ == "__main__":
    main()

# python scripts/visualize_outputs_summary.py