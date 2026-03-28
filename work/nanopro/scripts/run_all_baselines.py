#!/usr/bin/env python3
"""
一次性并行运行所有 baseline benchmarks 的脚本。

用法:
    python run_all_baselines.py [--model MODEL] [--threads N]

输出目录:
    assets/experiments/exp_baseline_YYYYMMDD_{clock}/
        results/           # 各 benchmark JSON 结果
        transcripts/        # 所有轨迹文件
        failure_cases/      # 失败案例分析
        dashboard.html      # 可视化页面
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import concurrent.futures
import threading
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('/Volumes/F/Clauding/.env')

# 添加项目根目录到 Python 路径
script_dir = Path(__file__).parent
_root_dir = script_dir.parent
sys.path.insert(0, str(_root_dir))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_all_baselines")

# 全局锁，用于写文件
_write_lock = threading.Lock()

# ============ 配置 ============
MODEL = os.environ.get('MODEL', 'google/gemini-3-flash-preview')
API_URL = os.environ.get('OPENAI_BASE_URL', '')
API_KEY = os.environ.get('OPENAI_API_KEY', '')
TIMEOUT = int(os.environ.get('TIMEOUT', '120'))

BENCHMARKS = [
    ('pinchbench', 'PinchBench'),
    ('openclawbench', 'OpenClawBench'),
    ('skillsbench', 'SkillsBench'),
    ('clawbench_official', 'ClawBench-Official'),
    ('claw-bench-tribe', 'ClawBench-TRIBE'),
    ('skillbench', 'SkillBench'),
]

MAX_WORKERS = 6  # 并行数


def get_exp_dir(base_dir: Path) -> Path:
    """创建带时间戳的实验目录"""
    clock = int(time.time())
    exp_dir = base_dir / f'exp_baseline_{datetime.now().strftime("%Y%m%d")}_{clock}'
    return exp_dir


def run_single_benchmark(benchmark_name: str, display_name: str, exp_dir: Path,
                          model: str, api_url: str, api_key: str,
                          timeout: int, threads: int = 4) -> dict:
    """
    运行单个 benchmark，返回结果。
    """
    nanopro_dir = _root_dir
    output_dir = exp_dir / 'results'
    transcript_dir = exp_dir / 'transcripts'

    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir.mkdir(parents=True, exist_ok=True)

    log_dir = exp_dir / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    # 构建命令
    cmd = [
        sys.executable,
        str(script_dir / 'run.py'),
        '--benchmark', benchmark_name,
        '--model', model,
        '--timeout', str(timeout),
        '--output-dir', str(output_dir),
        '--transcript-dir', str(transcript_dir),
    ]

    # 只有非空时才传递 API 参数，让 run.py 从 .env 加载
    if api_url:
        cmd.extend(['--api-url', api_url])
    if api_key:
        cmd.extend(['--api-key', api_key])

    if benchmark_name in ('skillsbench', 'clawbench_official'):
        cmd.extend(['--threads', str(threads)])

    log_file = log_dir / f'{benchmark_name}.log'

    logger.info(f"[{display_name}] Starting...")

    start_time = time.time()

    try:
        with open(log_file, 'w') as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(_root_dir),
                env={**os.environ,
                     'PYTHONPATH': str(_root_dir),
                     'PYTHONUNBUFFERED': '1'}
            )

            # 实时写日志
            for line in proc.stdout:
                lf.write(line)
                lf.flush()
                # 同时打印到控制台
                print(f"[{display_name}] {line}", end='')

            proc.wait()

        elapsed = time.time() - start_time
        logger.info(f"[{display_name}] Completed in {elapsed:.1f}s")

        # 读取结果
        result_files = list(output_dir.glob(f'{benchmark_name.replace("-", "_")}*.json'))
        if result_files:
            # 取最新的
            latest = max(result_files, key=lambda p: p.stat().st_mtime)
            with open(latest) as f:
                data = json.load(f)
            return {
                'benchmark': benchmark_name,
                'display_name': display_name,
                'score': data.get('overall_score', 0),
                'passed': data.get('passed_tasks', data.get('passed', 0)),
                'total': data.get('total_tasks', 0),
                'elapsed': elapsed,
                'result_file': str(latest),
                'success': True,
            }
        else:
            return {
                'benchmark': benchmark_name,
                'display_name': display_name,
                'score': 0,
                'passed': 0,
                'total': 0,
                'elapsed': elapsed,
                'success': False,
                'error': 'No result file found',
            }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{display_name}] Error: {e}")
        return {
            'benchmark': benchmark_name,
            'display_name': display_name,
            'score': 0,
            'passed': 0,
            'total': 0,
            'elapsed': elapsed,
            'success': False,
            'error': str(e),
        }


def export_failure_cases(exp_dir: Path) -> dict:
    """
    从结果中导出失败案例，保存到 failure_cases/ 目录。
    """
    output_dir = exp_dir / 'results'
    failure_dir = exp_dir / 'failure_cases'
    failure_dir.mkdir(parents=True, exist_ok=True)

    transcript_dir = exp_dir / 'transcripts'

    all_failures = {}

    for result_file in output_dir.glob('*.json'):
        benchmark_name = result_file.stem  # 如 pinchbench_1774660085668

        # 找到对应的benchmark名
        bench_key = benchmark_name.rsplit('_', 1)[0]  # 如 pinchbench

        try:
            with open(result_file) as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {result_file}: {e}")
            continue

        # 提取失败案例
        task_results = data.get('task_results', data.get('results', []))
        failures = []

        for task in task_results:
            # 判断是否失败
            passed = task.get('passed', False) or task.get('score', 0) == 1.0
            if not passed:
                task_id = task.get('task_id', task.get('id', 'unknown'))
                failures.append({
                    'task_id': task_id,
                    'benchmark': bench_key,
                    'score': task.get('score', 0),
                    'error': task.get('error', task.get('reason', 'unknown')),
                    'transcript': task.get('transcript', ''),
                })

        if failures:
            all_failures[bench_key] = failures

            # 保存该 benchmark 的失败案例
            failure_file = failure_dir / f'{bench_key}_failed.json'
            with open(failure_file, 'w') as f:
                json.dump({
                    'benchmark': bench_key,
                    'total_tasks': len(task_results),
                    'passed': len(task_results) - len(failures),
                    'failed': len(failures),
                    'failures': failures,
                }, f, indent=2)

            # 复制对应的 transcripts
            for fail in failures:
                task_id = fail['task_id']
                # 查找 transcript 文件
                for tf in transcript_dir.glob(f'{bench_key}_*.jsonl'):
                    # transcript 文件名格式可能是 {bench_key}_{task_id}.jsonl
                    pass  # 需要检查实际的 transcript 文件名格式

    # 保存汇总
    summary_file = failure_dir / 'manifest.md'
    with open(summary_file, 'w') as f:
        f.write("# Failure Cases Manifest\n\n")
        total_failures = sum(len(v) for v in all_failures.values())
        f.write(f"Total failures across all benchmarks: {total_failures}\n\n")
        for bench, failures in all_failures.items():
            f.write(f"- {bench}: {len(failures)} failures\n")

    logger.info(f"Exported {total_failures} failure cases to {failure_dir}")

    return {
        'total_failures': total_failures,
        'by_benchmark': {k: len(v) for k, v in all_failures.items()},
    }


def copy_transcripts_to_failure_cases(exp_dir: Path):
    """
    将失败案例的 transcripts 也复制到 failure_cases/ 目录。
    """
    failure_dir = exp_dir / 'failure_cases'
    transcript_dir = exp_dir / 'transcripts'

    if not transcript_dir.exists():
        return

    # 遍历所有失败案例 JSON 文件
    for failure_file in failure_dir.glob('*_failed.json'):
        try:
            with open(failure_file) as f:
                data = json.load(f)
        except:
            continue

        bench_key = data.get('benchmark', '')
        failures = data.get('failures', [])

        for fail in failures:
            task_id = fail.get('task_id', '')
            if not task_id:
                continue

            # 查找对应的 transcript 文件
            # 可能的格式: {bench_key}_{task_id}.jsonl, {task_id}.jsonl
            patterns = [
                f'{bench_key}_{task_id}.jsonl',
                f'{task_id}.jsonl',
            ]

            for pattern in patterns:
                src = transcript_dir / pattern
                if src.exists():
                    dst = failure_dir / pattern
                    shutil.copy2(src, dst)
                    break


def generate_dashboard(exp_dir: Path, benchmark_results: list):
    """
    生成 HTML 可视化 dashboard。
    """
    try:
        import pandas as pd

        # 准备数据
        rows = []
        for r in benchmark_results:
            if r['success']:
                rows.append({
                    'Benchmark': r['display_name'],
                    'Score (%)': r['score'],
                    'Passed': r['passed'],
                    'Total': r['total'],
                    'Time (s)': r['elapsed'],
                })

        if not rows:
            logger.warning("No successful results to visualize")
            return

        df = pd.DataFrame(rows)
        df = df.sort_values('Score (%)', ascending=False)

        # 生成 HTML
        html_path = exp_dir / 'dashboard.html'

        # 计算 overall
        total_passed = df['Passed'].sum()
        total_tasks = df['Total'].sum()
        overall_score = (total_passed / total_tasks * 100) if total_tasks > 0 else 0

        table_rows = ""
        for _, row in df.iterrows():
            score_color = '#4ade80' if row['Score (%)'] >= 70 else '#fbbf24' if row['Score (%)'] >= 50 else '#f87171'
            table_rows += f"""
            <tr>
                <td>{row['Benchmark']}</td>
                <td style="color: {score_color}; font-weight: bold;">{row['Score (%)']:.1f}%</td>
                <td>{row['Passed']}/{row['Total']}</td>
                <td>{row['Time (s)']:.1f}s</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Baseline Results Dashboard</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #f8fafc; margin-bottom: 0.5rem; }}
.subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}
.summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; }}
.card-label {{ font-size: 0.875rem; color: #94a3b8; margin-bottom: 0.5rem; }}
.card-value {{ font-size: 2rem; font-weight: 700; }}
.card-value.green {{ color: #4ade80; }}
.card-value.yellow {{ color: #fbbf24; }}
table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
th {{ background: #334155; padding: 1rem; text-align: left; font-size: 0.875rem; color: #94a3b8; }}
td {{ padding: 1rem; border-top: 1px solid #334155; }}
tr:hover {{ background: #263344; }}
.benchmark-bar {{ height: 8px; background: #334155; border-radius: 4px; margin-top: 0.5rem; overflow: hidden; }}
.benchmark-fill {{ height: 100%; border-radius: 4px; transition: width 1s ease; }}
</style>
</head>
<body>
<div class="container">
    <h1>📊 Baseline Results Dashboard</h1>
    <p class="subtitle">Experiment: {exp_dir.name} | Model: {MODEL}</p>

    <div class="summary-cards">
        <div class="card">
            <div class="card-label">Overall Score</div>
            <div class="card-value {'green' if overall_score >= 70 else 'yellow'}">{overall_score:.1f}%</div>
        </div>
        <div class="card">
            <div class="card-label">Total Passed</div>
            <div class="card-value green">{total_passed}/{total_tasks}</div>
        </div>
        <div class="card">
            <div class="card-label">Benchmarks</div>
            <div class="card-value">{len(df)}</div>
        </div>
        <div class="card">
            <div class="card-label">Total Cost</div>
            <div class="card-value">~${total_tasks * 0.01:.2f}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Benchmark</th>
                <th>Score</th>
                <th>Passed/Total</th>
                <th>Time</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
</div>
</body>
</html>"""

        with open(html_path, 'w') as f:
            f.write(html)

        logger.info(f"Dashboard saved to {html_path}")

    except ImportError:
        logger.warning("pandas not available, skipping dashboard generation")


def main():
    parser = argparse.ArgumentParser(description='Run all baseline benchmarks in parallel')
    parser.add_argument('--model', type=str, default=MODEL, help='Model to use')
    parser.add_argument('--threads', type=int, default=4, help='Threads per benchmark')
    parser.add_argument('--timeout', type=int, default=TIMEOUT, help='Timeout per task (seconds)')
    parser.add_argument('--exp-dir', type=str, default=None, help='Experiment directory (auto-generated if not set)')

    args = parser.parse_args()

    nanopro_dir = _root_dir
    assets_dir = nanopro_dir / 'assets' / 'experiments'

    # 创建实验目录
    if args.exp_dir:
        exp_dir = Path(args.exp_dir)
    else:
        exp_dir = get_exp_dir(assets_dir)

    exp_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=" * 60)
    logger.info(f"Experiment Directory: {exp_dir}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Threads per benchmark: {args.threads}")
    logger.info(f"=" * 60)

    # 写入实验配置
    config = {
        'model': args.model,
        'timestamp': datetime.now().isoformat(),
        'timeout': args.timeout,
        'threads': args.threads,
        'benchmarks': [b[0] for b in BENCHMARKS],
    }
    with open(exp_dir / 'config.json', 'w') as f:
        json.dump(config, f, indent=2)

    # 并行运行所有 benchmarks
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                run_single_benchmark,
                bm[0], bm[1], exp_dir,
                args.model, API_URL, API_KEY,
                args.timeout, args.threads
            ): bm
            for bm in BENCHMARKS
        }

        for future in concurrent.futures.as_completed(futures):
            bm = futures[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"[{bm[1]}] Result: {result['score']:.1f}% ({result['passed']}/{result['total']})")
            except Exception as e:
                logger.error(f"[{bm[1]}] Exception: {e}")
                results.append({
                    'benchmark': bm[0],
                    'display_name': bm[1],
                    'score': 0, 'passed': 0, 'total': 0,
                    'elapsed': 0, 'success': False,
                    'error': str(e),
                })

    # 导出失败案例
    logger.info("\n" + "=" * 60)
    logger.info("Exporting failure cases...")
    failure_stats = export_failure_cases(exp_dir)
    copy_transcripts_to_failure_cases(exp_dir)

    # 生成 Dashboard
    logger.info("\n" + "=" * 60)
    logger.info("Generating HTML dashboard...")
    generate_dashboard(exp_dir, results)

    # 保存汇总结果
    summary = {
        'experiment': str(exp_dir.name),
        'model': args.model,
        'timestamp': datetime.now().isoformat(),
        'results': results,
        'failure_stats': failure_stats,
    }

    with open(exp_dir / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    # 打印最终结果
    print("\n" + "=" * 60)
    print("ALL BASELINES COMPLETED")
    print("=" * 60)
    print(f"\nExperiment: {exp_dir.name}")
    print(f"Model: {args.model}")
    print("\nResults:")

    total_passed = 0
    total_tasks = 0

    for r in sorted(results, key=lambda x: -x['score']):
        if r['success']:
            print(f"  {r['display_name']}: {r['score']:.1f}% ({r['passed']}/{r['total']}) - {r['elapsed']:.1f}s")
            total_passed += r['passed']
            total_tasks += r['total']
        else:
            print(f"  {r['display_name']}: FAILED - {r.get('error', 'unknown')}")

    if total_tasks > 0:
        overall = total_passed / total_tasks * 100
        print(f"\nOverall: {overall:.1f}% ({total_passed}/{total_tasks})")

    print(f"\nResults saved to: {exp_dir}")
    print(f"Failure cases: {failure_stats.get('total_failures', 0)}")
    print("=" * 60)


if __name__ == '__main__':
    main()
