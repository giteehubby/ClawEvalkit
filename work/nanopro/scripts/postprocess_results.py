#!/usr/bin/env python3
"""
后处理脚本：从实验结果目录提取失败案例，生成 failure_cases 和可视化。

用法:
    python postprocess_results.py --exp-dir PATH
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from collections import Counter

script_dir = Path(__file__).parent
_root_dir = script_dir.parent
sys.path.insert(0, str(_root_dir))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("postprocess")


def load_tasks_from_result(result_file: Path) -> tuple:
    """
    从结果文件加载任务列表，返回 (benchmark_name, task_scores_dict)
    """
    with open(result_file) as f:
        data = json.load(f)

    benchmark = data.get('benchmark', result_file.stem.rsplit('_', 1)[0])
    task_scores = data.get('task_scores', {})

    return benchmark, task_scores


def is_task_passed(task_id: str, task_data: dict, benchmark: str) -> bool:
    """
    判断任务是否通过。不同 benchmark 格式不同。
    """
    # 方式1: 显式 passed 字段（必须是 True/False，不是 None）
    if 'passed' in task_data and isinstance(task_data['passed'], bool):
        return bool(task_data['passed'])

    # 方式2: mean 字段 (区分 0-1 分数 和 0-100 百分比)
    if 'mean' in task_data:
        mean = task_data['mean']
        if isinstance(mean, (int, float)):
            if mean <= 1.0:
                # 0-1 scale: mean >= 1.0 means passed
                return mean >= 1.0
            else:
                # 0-100 scale: mean >= 70 means passed (unless benchmark-specific)
                # 但 claw_bench_tribe 用 0-1 scale (passed=True/False)
                # skillsbench 用 0-100 scale
                # openclawbench 和 pinchbench 用 0-100 scale
                return mean >= 70.0

    # 方式3: score == 1.0
    if 'score' in task_data:
        return task_data['score'] == 1.0

    return True  # 默认通过


def get_task_error(task_data: dict) -> str:
    """从 task_data 中提取错误信息"""
    for key in ['error', 'reason', 'failure_reason', 'message']:
        if key in task_data and task_data[key]:
            return task_data[key]
    return 'unknown'


def get_task_prompt(task_data: dict) -> str:
    """从 task_data 中提取 prompt/instructions"""
    for key in ['prompt', 'instructions', 'task_prompt', 'query']:
        if key in task_data and task_data[key]:
            return task_data[key]
    return task_data.get('task_name', 'No prompt available')


def export_failure_cases(exp_dir: Path) -> dict:
    """从结果中导出失败案例"""
    output_dir = exp_dir / 'results'
    failure_dir = exp_dir / 'failure_cases'
    transcript_dir = exp_dir / 'transcripts'

    failure_dir.mkdir(parents=True, exist_ok=True)

    all_failures = {}
    total_failures = 0

    for result_file in sorted(output_dir.glob('*.json')):
        benchmark_name = result_file.stem.rsplit('_', 1)[0]

        try:
            with open(result_file) as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {result_file}: {e}")
            continue

        task_scores = data.get('task_scores', {})

        failures = []
        for task_id, task_data in task_scores.items():
            passed = is_task_passed(task_id, task_data, benchmark_name)

            if not passed:
                # 尝试获取 transcript
                transcript = ''

                # 在 transcripts/ 目录中查找
                if transcript_dir.exists():
                    for pattern in [
                        f'{task_id}_0.jsonl',
                        f'{task_id}.jsonl',
                        f'{benchmark_name}_{task_id}_0.jsonl',
                    ]:
                        tf = transcript_dir / pattern
                        if tf.exists():
                            try:
                                with open(tf) as f:
                                    lines = f.readlines()
                                # 合并成单个文本
                                transcript_parts = []
                                for line in lines:
                                    try:
                                        entry = json.loads(line)
                                        msg = entry.get('message', '')
                                        if isinstance(msg, dict):
                                            # 格式: {"type": "message", "message": {"role": ..., "content": ...}}
                                            content = msg.get('content', '')
                                            if content:
                                                transcript_parts.append(str(content))
                                        elif isinstance(msg, str) and msg:
                                            transcript_parts.append(msg)
                                        elif isinstance(msg, list):
                                            for m in msg:
                                                if isinstance(m, dict):
                                                    c = m.get('content', m.get('text', ''))
                                                    if c:
                                                        transcript_parts.append(str(c))
                                    except Exception:
                                        pass
                                transcript = '\n'.join(transcript_parts)
                            except Exception as e:
                                logger.debug(f"Failed to read transcript {tf}: {e}")
                            break

                # 也尝试从 result 文件的 task_data 中获取
                if not transcript:
                    transcript = task_data.get('transcript', task_data.get('message', ''))

                failures.append({
                    'task_id': task_id,
                    'task_name': task_data.get('task_name', task_id),
                    'score': task_data.get('mean', task_data.get('score', 0)),
                    'category': task_data.get('category', ''),
                    'difficulty': task_data.get('difficulty', ''),
                    'error': get_task_error(task_data),
                    'prompt': get_task_prompt(task_data),
                    'transcript': transcript,
                })

        if failures:
            all_failures[benchmark_name] = failures
            total_failures += len(failures)

            failure_file = failure_dir / f'{benchmark_name}_failed.json'
            with open(failure_file, 'w') as f:
                json.dump({
                    'benchmark': benchmark_name,
                    'total_tasks': len(task_scores),
                    'passed': len(task_scores) - len(failures),
                    'failed': len(failures),
                    'failures': failures,
                }, f, indent=2, ensure_ascii=False)

            logger.info(f"  {benchmark_name}: {len(failures)} failures")

    # 保存 manifest
    manifest_file = failure_dir / 'manifest.md'
    with open(manifest_file, 'w') as f:
        f.write("# Failure Cases Manifest\n\n")
        f.write(f"Total failures: {total_failures}\n\n")
        for bench, fails in sorted(all_failures.items()):
            pct = len(fails) / max(1, sum(len(v) for v in all_failures.values())) * 100
            f.write(f"- **{bench}**: {len(fails)} failures\n")
        f.write("\n## Failed Task IDs\n\n")
        for bench, fails in sorted(all_failures.items()):
            task_ids = [f['task_id'] for f in fails]
            f.write(f"### {bench}\n")
            f.write(f"```\n" + "\n".join(task_ids) + "\n```\n\n")

    logger.info(f"\nTotal: {total_failures} failures across {len(all_failures)} benchmarks")

    return {
        'total_failures': total_failures,
        'by_benchmark': {k: len(v) for k, v in all_failures.items()},
    }


def generate_dashboard(exp_dir: Path) -> dict:
    """生成 HTML 可视化 dashboard"""
    output_dir = exp_dir / 'results'

    results = []

    for result_file in sorted(output_dir.glob('*.json')):
        benchmark_name = result_file.stem.rsplit('_', 1)[0]

        try:
            with open(result_file) as f:
                data = json.load(f)
        except:
            continue

        task_scores = data.get('task_scores', {})
        total = len(task_scores)
        passed = sum(1 for tid, td in task_scores.items() if is_task_passed(tid, td, benchmark_name))

        # overall_score 可以直接用
        score = data.get('overall_score', 0)
        if score > 1:  # 0-100 scale
            score_pct = score
        else:  # 0-1 scale
            score_pct = score * 100

        results.append({
            'benchmark': benchmark_name,
            'score': score_pct,
            'passed': passed,
            'total': total,
        })

    if not results:
        logger.warning("No results to visualize")
        return {}

    total_passed = sum(r['passed'] for r in results)
    total_tasks = sum(r['total'] for r in results)
    overall = total_passed / total_tasks * 100 if total_tasks > 0 else 0

    # 排序
    results.sort(key=lambda x: -x['score'])

    rows_html = ""
    for r in results:
        score_color = '#4ade80' if r['score'] >= 70 else '#fbbf24' if r['score'] >= 50 else '#f87171'
        bar_width = r['score']
        rows_html += f"""
        <tr>
            <td>{r['benchmark']}</td>
            <td>
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <span style="color: {score_color}; font-weight: bold; min-width: 60px;">{r['score']:.1f}%</span>
                    <div style="flex: 1; background: #334155; border-radius: 4px; height: 8px; overflow: hidden;">
                        <div style="width: {bar_width}%; height: 100%; background: {score_color};"></div>
                    </div>
                </div>
            </td>
            <td>{r['passed']}/{r['total']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Baseline Results Dashboard</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem; }}
.container {{ max-width: 1100px; margin: 0 auto; }}
h1 {{ color: #f8fafc; margin-bottom: 0.5rem; }}
.subtitle {{ color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }}
.tldr {{ background: #1e3a5f; border-left: 4px solid #60a5fa; padding: 1rem; border-radius: 8px; margin-bottom: 2rem; }}
.tldr-label {{ font-size: 0.75rem; color: #60a5fa; font-weight: 700; margin-bottom: 0.25rem; }}
.tldr-text {{ font-size: 0.9rem; color: #bfdbfe; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
.sum-card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; text-align: center; }}
.sum-label {{ font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.5rem; }}
.sum-val {{ font-size: 2rem; font-weight: 700; }}
.sum-val.green {{ color: #4ade80; }}
.sum-val.yellow {{ color: #fbbf24; }}
.sum-val.red {{ color: #f87171; }}
table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
th {{ background: #334155; padding: 1rem; text-align: left; font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
td {{ padding: 1rem; border-top: 1px solid #334155; }}
tr:hover {{ background: #263344; }}
</style>
</head>
<body>
<div class="container">
    <h1>📊 Baseline Results Dashboard</h1>
    <p class="subtitle">Experiment: {exp_dir.name}</p>

    <div class="tldr">
        <div class="tldr-label">TLDR</div>
        <div class="tldr-text">Ran all 6 benchmarks. Overall pass rate: {overall:.1f}% ({total_passed}/{total_tasks}). Best: {results[0]['benchmark']} ({results[0]['score']:.1f}%), Weakest: {results[-1]['benchmark']} ({results[-1]['score']:.1f}%).</div>
    </div>

    <div class="summary">
        <div class="sum-card">
            <div class="sum-label">Overall Score</div>
            <div class="sum-val {'green' if overall >= 70 else 'yellow' if overall >= 50 else 'red'}">{overall:.1f}%</div>
        </div>
        <div class="sum-card">
            <div class="sum-label">Total Passed</div>
            <div class="sum-val green">{total_passed}/{total_tasks}</div>
        </div>
        <div class="sum-card">
            <div class="sum-label">Benchmarks</div>
            <div class="sum-val">{len(results)}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Benchmark</th>
                <th>Score</th>
                <th>Passed/Total</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</div>
</body>
</html>"""

    html_path = exp_dir / 'dashboard.html'
    with open(html_path, 'w') as f:
        f.write(html)

    logger.info(f"Dashboard saved to {html_path}")

    return {
        'overall': overall,
        'total_passed': total_passed,
        'total_tasks': total_tasks,
        'by_benchmark': {r['benchmark']: r['score'] for r in results},
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--exp-dir', type=str, required=True)
    args = parser.parse_args()

    exp_dir = Path(args.exp_dir)
    if not exp_dir.exists():
        logger.error(f"Directory not found: {exp_dir}")
        sys.exit(1)

    logger.info(f"Processing: {exp_dir}")

    # 1. 导出失败案例
    logger.info("\n=== Exporting Failure Cases ===")
    failure_stats = export_failure_cases(exp_dir)

    # 2. 生成 Dashboard
    logger.info("\n=== Generating Dashboard ===")
    dashboard_stats = generate_dashboard(exp_dir)

    # 3. 保存汇总
    summary_file = exp_dir / 'summary.json'
    summary = {
        'experiment': exp_dir.name,
        'dashboard': dashboard_stats,
        'failures': failure_stats,
    }
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("POSTPROCESSING COMPLETED")
    print("=" * 60)
    print(f"Total failures: {failure_stats['total_failures']}")
    print(f"Overall score: {dashboard_stats.get('overall', 'N/A'):.1f}%")
    print(f"Results in: {exp_dir}")
    print("=" * 60)


if __name__ == '__main__':
    main()
