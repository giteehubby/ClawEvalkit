#!/usr/bin/env python3
"""
统计各 Benchmark 实际参与测试的 Task 数量（与 run.py 过滤逻辑一致）。
- Multimodal 过滤：默认开启，仅 claweval 有 tags: [multimodal] 任务
- SkillsBench：根据 use_docker 跳过不同任务集合
- 其他 Benchmark：使用代码中硬编码的 TASK_COUNT

输出：benchmarks_task_counts.md
"""

import argparse
import ast
import re
from pathlib import Path


def extract_set_from_py(py_content: str, var_name: str) -> set:
    """用 AST 从 Python 源码中解析 SKIP_TASKS = {...} 这样的集合常量。"""
    try:
        tree = ast.parse(py_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == var_name:
                        if isinstance(node.value, ast.Set):
                            result = set()
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    result.add(str(elt.value))
                                elif isinstance(elt, ast.Str):  # Python 3.7 compat
                                    result.add(str(elt.s))
                            return result
        return set()
    except Exception:
        return set()


def count_claweval(tasks_dir: Path, exclude_multimodal: bool) -> tuple[int, int, int]:
    """ClawEval: 解析 task.yaml tags 字段，统计 multimodal 任务。"""
    import yaml

    total = 0
    multimodal = 0
    for t in tasks_dir.iterdir():
        if t.is_dir():
            total += 1
            yaml_file = t / "task.yaml"
            if yaml_file.exists():
                data = yaml.safe_load(yaml_file.read_text())
                tags = data.get("tags", []) or []
                if "multimodal" in tags:
                    multimodal += 1
    after = total - multimodal if exclude_multimodal else total
    return total, multimodal, after


def count_agentbench(tasks_base: Path) -> int:
    """AgentBench: 遍历 tasks/{category}/*/task.yaml 计数。"""
    import yaml

    total = 0
    for cat in tasks_base.iterdir():
        if cat.is_dir():
            for task_dir in cat.iterdir():
                if task_dir.is_dir() and (task_dir / "task.yaml").exists():
                    total += 1
    return total


def count_pinchbench(tasks_dir: Path) -> int:
    """PinchBench: 统计 task_*.md 文件数量（不含 TEMPLATE）。"""
    if not tasks_dir.exists():
        return 0
    return len([f for f in tasks_dir.glob("task_*.md")])


def main():
    parser = argparse.ArgumentParser(description="统计各 Benchmark 实际参与测试的 Task 数量")
    parser.add_argument("--include-multimodal", action="store_true", help="包含 multimodal 任务（默认排除）")
    parser.add_argument("--output", default="benchmarks_task_counts.md", help="输出文件路径")
    args = parser.parse_args()

    exclude_multimodal = not args.include_multimodal
    root = Path(__file__).resolve().parent.parent
    ds_dir = root / "clawevalkit" / "dataset"

    rows = []

    # ========================
    # ZClawBench
    # ========================
    zclaw_json = root / "benchmarks" / "zclawbench" / "tasks.json"
    if zclaw_json.exists():
        import json

        data = json.loads(zclaw_json.read_text())
        total = data.get("total_tasks", 116)
        # Docker 模式 116，非 Docker 模式 18
        after_docker = total
        after_native = 18
        rows.append(
            (
                "zclawbench",
                total,
                "0",
                f"**{after_docker}** (docker) / {after_native} (native)",
                "无 multimodal 过滤",
            )
        )

    # ========================
    # ClawEval（唯一有 multimodal 过滤的 benchmark）
    # ========================
    claweval_tasks = root / "benchmarks" / "claw-eval" / "tasks"
    if claweval_tasks.exists():
        total, multimodal, after = count_claweval(claweval_tasks, exclude_multimodal)
        rows.append(
            (
                "claweval",
                total,
                str(multimodal),
                f"**{after}**",
                "默认排除 tags: [multimodal] 任务",
            )
        )

    # ========================
    # PinchBench
    # ========================
    pinch_tasks = root / "benchmarks" / "pinchbench" / "tasks"
    if pinch_tasks.exists():
        total = count_pinchbench(pinch_tasks)
        rows.append(("pinchbench", total, "0", f"**{total}**", "无 multimodal 过滤"))

    # ========================
    # AgentBench
    # ========================
    agent_tasks = root / "benchmarks" / "agentbench-openclaw" / "tasks"
    if agent_tasks.exists():
        total = count_agentbench(agent_tasks)
        rows.append(("agentbench", total, "0", f"**{total}**", "无 multimodal 过滤"))

    # ========================
    # SkillsBench（从源码解析 SKIP_TASKS，保持同步）
    # ========================
    skillsbench_py = ds_dir / "skillsbench.py"
    if skillsbench_py.exists():
        content = skillsbench_py.read_text()
        skip_tasks = extract_set_from_py(content, "SKIP_TASKS")
        easy_skip_tasks = extract_set_from_py(content, "EASY_SKIP_TASKS")

        tasks_dir = root / "benchmarks" / "skillsbench" / "tasks"
        if tasks_dir.exists():
            all_tasks = [d.name for d in tasks_dir.iterdir() if d.is_dir()]
            total = len(all_tasks)

            # Docker: 跳过 SKIP_TASKS；非 Docker: 跳过 SKIP_TASKS - EASY_SKIP_TASKS
            docker_skip = skip_tasks
            non_docker_skip = skip_tasks - easy_skip_tasks
            after_docker = total - len(docker_skip)
            after_native = total - len(non_docker_skip)
            rows.append(
                (
                    "skillsbench",
                    total,
                    f"{len(docker_skip)} (docker skip)",
                    f"**{after_docker}** (docker) / {after_native} (native)",
                    f"SKIP_TASKS={len(skip_tasks)}，EASY_SKIP_TASKS={len(easy_skip_tasks)}",
                )
            )

    # ========================
    # Tribe（硬编码）
    # ========================
    rows.append(("tribe", 8, "0", "**8**", "代码硬编码 TASK_COUNT=8"))

    # ========================
    # WildClawBench（硬编码）
    # ========================
    rows.append(("wildclawbench", 60, "0", "**60**", "代码硬编码 TASK_COUNT=60"))

    # ========================
    # ClawBench Official（硬编码）
    # ========================
    rows.append(("clawbench-official", 250, "0", "**250**", "代码硬编码 TASK_COUNT=250"))

    # ========================
    # SkillBench（硬编码）
    # ========================
    rows.append(("skillbench", 22, "0", "**22**", "代码硬编码 TASK_COUNT=22"))

    # ========================
    # 输出 Markdown
    # ========================
    md_lines = []
    md_lines.append("# Benchmarks Task Counts\n")
    md_lines.append(
        f"**统计时间**: 2026-05-01  |  **Multimodal 过滤**: {'开启（默认）' if exclude_multimodal else '关闭（--include-multimodal）'}\n"
    )
    md_lines.append(
        "| Benchmark | 总任务数 | 被过滤任务 | 实际参与数 | 备注 |"
    )
    md_lines.append("|-----------|---------|-----------|-----------|------|")
    for row in rows:
        bench, total, filtered, after, note = row
        md_lines.append(f"| {bench} | {total} | {filtered} | {after} | {note} |")

    md_lines.append("")
    md_lines.append(
        "**注**: `--exclude_multimodal` 是 run.py 的默认行为，仅 `claweval` 基准有 `tags: [multimodal]` 任务。"
    )

    content = "\n".join(md_lines)
    out_path = root / args.output
    out_path.write_text(content)
    print(f"已保存到: {out_path}")
    print()
    print(content)


if __name__ == "__main__":
    main()
