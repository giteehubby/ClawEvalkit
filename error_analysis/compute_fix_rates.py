#!/usr/bin/env python3
"""
统计 failure_categories_by_group.json 中各类错误在不同 harness 下的修复率。

修复率 = (baseline失败 且 harness重跑后通过的任务数) / 该类别下的总失败任务数

对于没有 harness 结果的任务，视为仍然失败（未修复）。

输出:
  - error_analysis/outputs/fix_rates.json               完整统计（含 task 列表）
  - error_analysis/outputs/fix_rates_overall.png         总体修复率柱状图
  - error_analysis/outputs/fix_rates_by_bench.png        按 bench 分组柱状图
  - error_analysis/outputs/fix_rates_pie_grid.png        饼状图矩阵（cat × bench × harness）
"""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
CATEGORIES_FILE = Path(__file__).resolve().parent / "outputs" / "failure_categories_by_group.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
HARNESS_DIR = BASE_DIR / "outputs" / "harness"
MODEL = "glm-4.7"

HARNESS_LIST = ["control", "memory", "collaboration", "procedure"]
CATEGORIES_ORDERED = ["A", "B", "C", "D", "E", "F"]
BENCHES_ORDERED = ["agentbench", "clawbench", "claweval"]

CATEGORY_NAMES = {
    "A": "A: Task Understanding / Planning Drift",
    "B": "B: Tool / Environment Grounding Failure",
    "C": "C: Memory / State Management Failure",
    "D": "D: Verification / Recovery Deficiency",
    "E": "E: Long-tail Procedural Knowledge / Skill Execution",
    "F": "F: Other / Mixed",
}

BENCH_DIR_MAP = {
    "agentbench": "agentbench",
    "clawbench": "clawbench-official",
    "claweval": "claweval",
}

BENCH_DISPLAY = {
    "agentbench": "AgentBench",
    "clawbench": "ClawBench",
    "claweval": "ClawEval",
}

# ClawBench task_id has two formats: short (cal-005) and long (cal-005-change-meeting-time).
# Build a mapping so we can normalize both failure list and result files to long names.
CLAWBENCH_TASKS_DIR = BASE_DIR / "benchmarks" / "claw-bench" / "tasks"


def _build_clawbench_id_map() -> dict[str, str]:
    """Build short_name -> canonical_name mapping from ClawBench task directories."""
    id_map: dict[str, str] = {}
    if not CLAWBENCH_TASKS_DIR.exists():
        return id_map
    for task_dir in CLAWBENCH_TASKS_DIR.rglob("*"):
        if not task_dir.is_dir():
            continue
        name = task_dir.name
        id_map[name] = name  # long name maps to itself
        # Extract short prefix: "cal-005-change-meeting-time" -> "cal-005"
        parts = name.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            short = f"{parts[0]}-{parts[1]}"
            id_map[short] = name
    return id_map



def load_categories():
    with open(CATEGORIES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    task_to_cat = {}
    for cat, entries in data["by_category"].items():
        for entry in entries:
            task_to_cat[(entry["bench"], entry["task_id"])] = cat
    return task_to_cat


def check_passed(bench, harness, task_id):
    bench_dir = BENCH_DIR_MAP[bench]
    base = HARNESS_DIR / harness / bench_dir / MODEL

    if bench == "agentbench":
        result_file = base / task_id / "result.json"
    elif bench == "clawbench":
        # 先用原始 id 找，找不到再走映射
        result_file = base / f"{task_id}.json"
        if not result_file.exists():
            id_map = _build_clawbench_id_map()
            canonical = id_map.get(task_id, task_id)
            if canonical != task_id:
                result_file = base / f"{canonical}.json"
    elif bench == "claweval":
        result_file = base / task_id / "result.json"
    else:
        return None

    if not result_file.exists():
        return None

    try:
        with open(result_file, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if bench == "agentbench":
        overall = data.get("scores", {}).get("overall_score", 0)
        return overall >= 90
    else:
        return data.get("passed", False) or data.get("score", 0) >= 0.9


def collect_detail(task_to_cat):
    """收集每个 (bench, category, harness) 下的 fixed / unfixed / not_run task 列表。"""
    detail = {}
    for bench in BENCHES_ORDERED:
        detail[bench] = {}
        bench_tasks = {(b, t): c for (b, t), c in task_to_cat.items() if b == bench}
        cats_in_bench = sorted(set(bench_tasks.values()))
        for cat in cats_in_bench:
            cat_tasks = [t for (b, t), c in bench_tasks.items() if c == cat]
            detail[bench][cat] = {}
            for h in HARNESS_LIST:
                fixed, unfixed, not_run = [], [], []
                for t in cat_tasks:
                    result = check_passed(bench, h, t)
                    if result is None:
                        not_run.append(t)
                    elif result:
                        fixed.append(t)
                    else:
                        unfixed.append(t)
                detail[bench][cat][h] = {
                    "total": len(cat_tasks),
                    "fixed": fixed,
                    "unfixed": unfixed,
                    "not_run": not_run,
                    "fixed_count": len(fixed),
                    "unfixed_count": len(unfixed),
                    "not_run_count": len(not_run),
                    "rate": round(len(fixed) / len(cat_tasks), 4) if cat_tasks else 0,
                }
    return detail


def build_json_output(task_to_cat, detail):
    result = {"overall": {}, "by_bench": {}}

    # Overall
    result["overall"] = _format_section(detail, bench_filter=None)

    # Per bench
    for bench in BENCHES_ORDERED:
        result["by_bench"][bench] = _format_section(detail, bench_filter=bench)

    return result


def _format_section(detail, bench_filter=None):
    benches = [bench_filter] if bench_filter else BENCHES_ORDERED
    section = {
        "total_failed_tasks": 0,
        "categories": {},
        "harness_summary": {},
    }

    # 收集该 section 涉及的所有 categories
    all_cats = set()
    for bench in benches:
        all_cats.update(detail[bench].keys())

    for cat in sorted(all_cats):
        label = CATEGORY_NAMES.get(cat, cat)
        cat_entry = {"name": label, "by_harness": {}}

        for h in HARNESS_LIST:
            total = sum(detail[bench].get(cat, {}).get(h, {}).get("total", 0) for bench in benches)
            fixed_list = []
            unfixed_list = []
            not_run_list = []
            for bench in benches:
                d = detail[bench].get(cat, {}).get(h, {})
                fixed_list.extend([f"{bench}:{t}" for t in d.get("fixed", [])])
                unfixed_list.extend([f"{bench}:{t}" for t in d.get("unfixed", [])])
                not_run_list.extend([f"{bench}:{t}" for t in d.get("not_run", [])])

            cat_entry["by_harness"][h] = {
                "total": total,
                "fixed_count": len(fixed_list),
                "unfixed_count": len(unfixed_list),
                "not_run_count": len(not_run_list),
                "rate": round(len(fixed_list) / total, 4) if total else 0,
                "fixed_tasks": fixed_list,
                "unfixed_tasks": unfixed_list,
                "not_run_tasks": not_run_list,
            }

        section["categories"][cat] = cat_entry

    # harness_summary
    all_tasks_count = sum(
        detail[bench].get(next(iter(detail[bench])), {}).get(HARNESS_LIST[0], {}).get("total", 0)
        if detail[bench] else 0
        for bench in benches
    )
    # 重新计算 total
    task_set = set()
    for bench in benches:
        for cat, cat_data in detail[bench].items():
            for t in cat_data.get(HARNESS_LIST[0], {}).get("fixed", []) + \
                     cat_data.get(HARNESS_LIST[0], {}).get("unfixed", []) + \
                     cat_data.get(HARNESS_LIST[0], {}).get("not_run", []):
                task_set.add((bench, t))
    section["total_failed_tasks"] = len(task_set)

    for h in HARNESS_LIST:
        all_fixed = sum(section["categories"][c]["by_harness"][h]["fixed_count"]
                        for c in section["categories"])
        all_total = sum(section["categories"][c]["by_harness"][h]["total"]
                        for c in section["categories"])
        section["harness_summary"][h] = {
            "total": all_total,
            "fixed": all_fixed,
            "rate": round(all_fixed / all_total, 4) if all_total else 0,
        }

    return section


def plot_overall(json_data):
    categories = list(json_data["overall"]["categories"].keys())
    x = np.arange(len(categories))
    width = 0.18
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = ["#8ecae6", "#219ebc", "#fb8500", "#cccccc"]

    for i, h in enumerate(HARNESS_LIST):
        rates = [json_data["overall"]["categories"][c]["by_harness"][h]["rate"] * 100
                 for c in categories]
        bars = ax.bar(x + i * width, rates, width, label=h, color=colors[i], edgecolor="white")
        for bar, rate in zip(bars, rates):
            if rate > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                        f"{rate:.0f}%", ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("Error Category")
    ax.set_ylabel("Fix Rate (%)")
    ax.set_title("Fix Rate by Error Category and Harness (Overall)")
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(categories)
    ax.legend(title="Harness")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.set_ylim(0, max(25, ax.get_ylim()[1] * 1.15))
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fix_rates_overall.png", dpi=150)
    plt.close(fig)


def plot_by_bench(json_data):
    benches = list(json_data["by_bench"].keys())
    n = len(benches)
    fig, axes = plt.subplots(1, n, figsize=(7 * n, 6), sharey=False)
    if n == 1:
        axes = [axes]
    colors = ["#8ecae6", "#219ebc", "#fb8500", "#cccccc"]

    for ax, bench in zip(axes, benches):
        bench_data = json_data["by_bench"][bench]
        categories = list(bench_data["categories"].keys())
        x = np.arange(len(categories))
        width = 0.18

        for i, h in enumerate(HARNESS_LIST):
            rates = [bench_data["categories"][c]["by_harness"][h]["rate"] * 100
                     for c in categories]
            bars = ax.bar(x + i * width, rates, width, label=h, color=colors[i], edgecolor="white")
            for bar, rate in zip(bars, rates):
                if rate > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                            f"{rate:.0f}%", ha="center", va="bottom", fontsize=7)

        ax.set_title(f"{bench}\n({bench_data['total_failed_tasks']} failed tasks)")
        ax.set_xlabel("Error Category")
        ax.set_xticks(x + width * 1.5)
        ax.set_xticklabels(categories)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter())

    axes[0].set_ylabel("Fix Rate (%)")
    axes[-1].legend(title="Harness", loc="upper right")
    fig.suptitle("Fix Rate by Error Category and Harness (Per Benchmark)", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "fix_rates_by_bench.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_crr_heatmap(json_data):
    """绘制 CRR (Category-level Recovery Rate) 热力图，匹配 Phase 4 矩阵格式。

    行 = harness conditions, 列 = error categories + Overall + NIR
    NIR (Net Improvement Rate) = 该harness的Overall CRR
    """
    categories = [c for c in CATEGORIES_ORDERED if c in json_data["overall"]["categories"]]

    # 构建矩阵: rows=harnesses, cols=categories + Overall + NIR
    matrix = []
    for h in HARNESS_LIST:
        row = []
        for c in categories:
            row.append(json_data["overall"]["categories"][c]["by_harness"][h]["rate"] * 100)
        # Overall
        row.append(json_data["overall"]["harness_summary"][h]["rate"] * 100)
        # NIR = Overall (即相对于 baseline=0 的净提升率)
        row.append(json_data["overall"]["harness_summary"][h]["rate"] * 100)
        matrix.append(row)

    matrix = np.array(matrix)
    col_labels = [f"Cat {c}" for c in categories] + ["Overall", "NIR"]
    harness_display = ["T2 (+Control)", "T1 (+Memory)", "T3 (+Collab)", "T4 (+Procedure)"]

    fig, ax = plt.subplots(figsize=(12, 4.5))

    vmax = max(matrix.max() * 1.15, 10)
    cmap = plt.cm.RdYlGn

    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)

    # 标注数值
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            # 分母
            if j < len(categories):
                total = json_data["overall"]["categories"][categories[j]]["by_harness"][HARNESS_LIST[i]]["total"]
                fixed = json_data["overall"]["categories"][categories[j]]["by_harness"][HARNESS_LIST[i]]["fixed_count"]
            elif j == len(categories):  # Overall
                total = json_data["overall"]["harness_summary"][HARNESS_LIST[i]]["total"]
                fixed = json_data["overall"]["harness_summary"][HARNESS_LIST[i]]["fixed"]
            else:  # NIR
                total = json_data["overall"]["harness_summary"][HARNESS_LIST[i]]["total"]
                fixed = json_data["overall"]["harness_summary"][HARNESS_LIST[i]]["fixed"]

            color = "white" if val > vmax * 0.5 else "black"
            label = f"{val:.1f}%\n({fixed}/{total})" if val > 0 else f"-\n({fixed}/{total})"
            ax.text(j, i, label, ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, fontsize=10)
    ax.set_yticks(range(len(harness_display)))
    ax.set_yticklabels(harness_display, fontsize=10)

    # 分隔线：Overall 和 NIR 之间
    sep_x = len(categories) - 0.5
    ax.axvline(x=sep_x + 1.5, color="gray", linewidth=1.5, linestyle="--", alpha=0.5)

    plt.colorbar(im, ax=ax, shrink=0.85, label="CRR (%)")

    ax.set_title("Category-level Recovery Rate (CRR) Matrix", fontsize=13, pad=12)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "crr_heatmap.png", dpi=150)
    plt.close(fig)

    # 按bench分组的热力图
    for bench in BENCHES_ORDERED:
        bench_data = json_data["by_bench"][bench]
        bench_cats = [c for c in CATEGORIES_ORDERED if c in bench_data["categories"]]

        bench_matrix = []
        for h in HARNESS_LIST:
            row = []
            for c in bench_cats:
                row.append(bench_data["categories"][c]["by_harness"][h]["rate"] * 100)
            row.append(bench_data["harness_summary"][h]["rate"] * 100)
            bench_matrix.append(row)

        bench_matrix = np.array(bench_matrix)
        bench_col_labels = [f"Cat {c}" for c in bench_cats] + ["Overall"]

        fig_b, ax_b = plt.subplots(figsize=(3 + len(bench_col_labels) * 1.2, 4))
        vmax_b = max(bench_matrix.max() * 1.15, 10) if bench_matrix.size else 10
        im_b = ax_b.imshow(bench_matrix, cmap=cmap, aspect="auto", vmin=0, vmax=vmax_b)

        for i in range(bench_matrix.shape[0]):
            for j in range(bench_matrix.shape[1]):
                val = bench_matrix[i, j]
                if j < len(bench_cats):
                    d = bench_data["categories"][bench_cats[j]]["by_harness"][HARNESS_LIST[i]]
                    fixed, total = d["fixed_count"], d["total"]
                else:
                    s = bench_data["harness_summary"][HARNESS_LIST[i]]
                    fixed, total = s["fixed"], s["total"]
                color = "white" if val > vmax_b * 0.5 else "black"
                label = f"{val:.1f}%\n({fixed}/{total})" if val > 0 else f"-\n({fixed}/{total})"
                ax_b.text(j, i, label, ha="center", va="center",
                          fontsize=9, fontweight="bold", color=color)

        ax_b.set_xticks(range(len(bench_col_labels)))
        ax_b.set_xticklabels(bench_col_labels, fontsize=10)
        ax_b.set_yticks(range(len(harness_display)))
        ax_b.set_yticklabels(harness_display, fontsize=10)

        bench_display_name = BENCH_DISPLAY.get(bench, bench)
        ax_b.set_title(f"CRR Matrix — {bench_display_name}\n({bench_data['total_failed_tasks']} failed tasks)",
                        fontsize=12, pad=10)
        plt.colorbar(im_b, ax=ax_b, shrink=0.85, label="CRR (%)")
        fig_b.tight_layout()
        fig_b.savefig(OUTPUT_DIR / f"crr_heatmap_{bench}.png", dpi=150)
        plt.close(fig_b)


def plot_pie_grid(detail):
    """绘制饼状图矩阵：6 categories × 3 benches 行，4 harnesses 列。"""
    n_cats = len(CATEGORIES_ORDERED)
    n_benches = len(BENCHES_ORDERED)
    n_harnesses = len(HARNESS_LIST)
    n_rows = n_cats * n_benches  # 18
    n_cols = n_harnesses          # 4

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 42))
    pie_colors = ["#2a9d8f", "#e76f51", "#cccccc"]  # fixed, unfixed, not_run

    for ci, cat in enumerate(CATEGORIES_ORDERED):
        for bi, bench in enumerate(BENCHES_ORDERED):
            row = ci * n_benches + bi
            for hi, h in enumerate(HARNESS_LIST):
                ax = axes[row][hi]
                d = detail[bench].get(cat, {}).get(h, None)

                if d is None:
                    ax.text(0.5, 0.5, "N/A", ha="center", va="center",
                            transform=ax.transAxes, fontsize=9, color="gray")
                    ax.set_xticks([])
                    ax.set_yticks([])
                    continue

                fixed_c = d["fixed_count"]
                unfixed_c = d["unfixed_count"]
                not_run_c = d["not_run_count"]
                total = d["total"]

                values = [fixed_c, unfixed_c, not_run_c]
                labels_legend = ["Fixed", "Unfixed", "Not Run"]
                draw_colors = [c for c, v in zip(pie_colors, values) if v > 0]
                draw_values = [v for v in values if v > 0]

                if sum(values) == 0:
                    ax.text(0.5, 0.5, "0 tasks", ha="center", va="center",
                            transform=ax.transAxes, fontsize=9, color="gray")
                    ax.set_xticks([])
                    ax.set_yticks([])
                else:
                    wedges, texts, autotexts = ax.pie(
                        draw_values,
                        colors=draw_colors,
                        autopct=lambda pct: f"{pct:.0f}%" if pct > 5 else "",
                        startangle=90,
                        pctdistance=0.55,
                        textprops={"fontsize": 7},
                    )
                    for at in autotexts:
                        at.set_fontweight("bold")
                        at.set_color("white")

                # 只在第一列标注 bench，只在第一行标注 harness
                if hi == 0:
                    bench_label = BENCH_DISPLAY.get(bench, bench)
                    ax.set_ylabel(f"{cat} | {bench_label}", fontsize=9,
                                  fontweight="bold", labelpad=2)
                if row == 0:
                    ax.set_title(h, fontsize=10, fontweight="bold")

    # 全局图例
    fig.legend(labels=["Fixed", "Unfixed", "Not Run"], loc="lower center",
               ncol=3, fontsize=11, frameon=False,
               bbox_to_anchor=(0.5, 0.01))

    fig.suptitle("Fix Status by Category × Bench × Harness", fontsize=16, y=0.995)
    fig.tight_layout(rect=[0, 0.025, 1, 0.99])
    fig.savefig(OUTPUT_DIR / "fix_rates_pie_grid.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    task_to_cat = load_categories()

    # 1. 收集详细数据
    detail = collect_detail(task_to_cat)

    # 2. 构建 JSON 并保存
    json_data = build_json_output(task_to_cat, detail)
    json_path = OUTPUT_DIR / "fix_rates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON saved: {json_path}")

    # 3. 生成图表
    plot_overall(json_data)
    print(f"Chart saved: {OUTPUT_DIR / 'fix_rates_overall.png'}")

    plot_by_bench(json_data)
    print(f"Chart saved: {OUTPUT_DIR / 'fix_rates_by_bench.png'}")

    plot_pie_grid(detail)
    print(f"Chart saved: {OUTPUT_DIR / 'fix_rates_pie_grid.png'}")

    # 5. CRR 热力图
    plot_crr_heatmap(json_data)
    print(f"Chart saved: {OUTPUT_DIR / 'crr_heatmap.png'}")
    for bench in BENCHES_ORDERED:
        p = OUTPUT_DIR / f"crr_heatmap_{bench}.png"
        if p.exists():
            print(f"Chart saved: {p}")

    # 4. 终端打印摘要
    print("\n" + "=" * 70)
    print("Fix Rate Summary")
    print("=" * 70)
    for h in HARNESS_LIST:
        s = json_data["overall"]["harness_summary"][h]
        print(f"  {h:<16} {s['fixed']:>3}/{s['total']:<3}  {s['rate']:.1%}")

    # CRR 矩阵表
    categories = [c for c in CATEGORIES_ORDERED if c in json_data["overall"]["categories"]]
    header = f"{'Condition':<20}" + "".join(f"Cat {c:>5}" for c in categories) + f"{'Overall':>9}{'NIR':>7}"
    print(f"\n{'=' * 70}")
    print("CRR Matrix (Category-level Recovery Rate)")
    print(f"{'=' * 70}")
    print(header)
    print("-" * 70)
    harness_display = {"control": "T2 (+Control)", "memory": "T1 (+Memory)",
                       "collaboration": "T3 (+Collab)", "procedure": "T4 (+Procedure)"}
    for h in HARNESS_LIST:
        label = harness_display.get(h, h)
        row = f"{label:<20}"
        for c in categories:
            r = json_data["overall"]["categories"][c]["by_harness"][h]["rate"]
            row += f"{r:>8.1%}"
        overall = json_data["overall"]["harness_summary"][h]["rate"]
        row += f"{overall:>9.1%}{overall:>7.1%}"
        print(row)
    print()


if __name__ == "__main__":
    main()

# python3 error_analysis/compute_fix_rates.py