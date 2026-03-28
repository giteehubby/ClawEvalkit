#!/usr/bin/env python3
"""
使用 LLM (gemini-3.1-pro-preview) 自动评估失败案例的类别。

五类错误:
    A: Planning / Reasoning Failure
    B: Tool Use Failure
    C: State Grounding Failure
    D: Execution Failure
    E: Knowledge / Skill Gap

用法:
    python evaluate_failures.py --exp-dir PATH [--max-samples N] [--threads N]
"""

import argparse
import json
import logging
import os
import sys
import time
import concurrent.futures
import threading
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv('/Volumes/F/Clauding/.env')

script_dir = Path(__file__).parent
_root_dir = script_dir.parent
sys.path.insert(0, str(_root_dir))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("evaluate_failures")

# ============ LLM 配置 ============
API_URL = os.environ.get('OPENAI_BASE_URL', 'https://openrouter.ai/api/v1')
API_KEY = os.environ.get('OPENAI_API_KEY', '')
EVAL_MODEL = 'google/gemini-3.1-pro-preview'

CATEGORIES = {
    'A': 'Planning / Reasoning Failure',
    'B': 'Tool Use Failure',
    'C': 'State Grounding Failure',
    'D': 'Execution Failure',
    'E': 'Knowledge / Skill Gap',
}

SYSTEM_PROMPT = """You are an expert at analyzing agent failure traces and categorizing them into failure types.

## Failure Categories

**A: Planning / Reasoning Failure**
Agent selects an inappropriate strategy or plan for the task, even though it may have correct domain knowledge.
- Indicators: wrong approach from start, over/under-complicates problem, logical planning errors, ignores task constraints
- Examples: trying web search for local file ops, writing code without understanding API

**B: Tool Use Failure**
Agent chooses correct high-level approach but fails to use tools correctly.
- Indicators: correct tool but wrong arguments, wrong tool call order, malformed tool calls, doesn't check tool output
- Examples: API call with incorrect parameters, wrong file path format, not handling return values

**C: State Grounding Failure**
Agent misunderstands or has incorrect model of the environment state.
- Indicators: assumes something exists that doesn't, doesn't know current state, misreads environment feedback, has stale info
- Examples: trying to edit non-existent file, assuming command succeeded when it failed

**D: Execution Failure**
Agent forms correct plan and has correct tool knowledge but fails during execution.
- Indicators: right approach but typos/syntax errors, correct tool+args but execution goes wrong, gets stuck in loops
- Examples: syntax error in code, correct plan but wrong variable name

**E: Knowledge / Skill Gap**
Agent lacks the specific knowledge or skill required to complete the task.
- Indicators: attempts task in domain it doesn't understand, doesn't know how to use specialized tools/APIs, lacks factual knowledge
- Examples: cannot interpret scientific data formats, missing domain-specific knowledge

## Output Format
You MUST respond with ONLY a valid JSON object, no markdown, no explanation:
{"category": "A|B|C|D|E", "confidence": 1-3, "reasoning": "brief explanation"}

- category: single letter A-E indicating the dominant failure type
- confidence: 1=low, 2=medium, 3=high confidence in this categorization
- reasoning: 1-2 sentences explaining why this category fits
"""


def build_evaluation_prompt(task_info: dict, transcript: str) -> str:
    """构造发送给 LLM 的评估 prompt"""

    task_id = task_info.get('task_id', 'unknown')
    benchmark = task_info.get('benchmark', 'unknown')
    error = task_info.get('error', 'No error info')
    prompt_text = task_info.get('prompt', task_info.get('instructions', 'No prompt available'))

    # 截取 transcript 关键部分（避免太长）
    max_transcript_len = 3000
    if len(transcript) > max_transcript_len:
        transcript = transcript[:max_transcript_len] + f"\n... [truncated, total {len(transcript)} chars]"

    prompt = f"""## Task to Analyze

- Task ID: {task_id}
- Benchmark: {benchmark}
- Error: {error}

## Task Prompt
{prompt_text}

## Agent Transcript (Failure Trace)
{transcript}

## Your Task
Analyze the above failure trace and determine the dominant failure category.

Respond with ONLY a valid JSON object:
{{"category": "A|B|C|D|E", "confidence": 1-3, "reasoning": "brief explanation"}}
"""

    return prompt


def evaluate_single_failure(task_info: dict, client: OpenAI, max_retries: int = 3) -> dict:
    """使用 LLM 评估单个失败案例"""
    task_id = task_info.get('task_id', 'unknown')
    benchmark = task_info.get('benchmark', 'unknown')

    for attempt in range(max_retries):
        try:
            prompt_text = build_evaluation_prompt(task_info, task_info.get('transcript', ''))

            response = client.chat.completions.create(
                model=EVAL_MODEL,
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt_text},
                ],
                temperature=0.1,
                max_tokens=1500,
            )

            raw_content = response.choices[0].message.content
            if raw_content is None:
                raise ValueError("LLM returned empty content")
            content = raw_content.strip()

            # 尝试解析 JSON
            try:
                # 去掉可能的 markdown 格式
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                result = json.loads(content.strip())

                return {
                    'task_id': task_id,
                    'benchmark': benchmark,
                    'category': result.get('category', 'U'),
                    'confidence': result.get('confidence', 0),
                    'reasoning': result.get('reasoning', ''),
                    'success': True,
                }

            except json.JSONDecodeError as e:
                # 尝试从截断的内容中提取 category
                import re
                cat_match = re.search(r'"category"\s*:\s*["\']?([A-E])["\']?', content)
                if cat_match:
                    logger.warning(f"[{benchmark}/{task_id}] Extracted category from truncated JSON: {cat_match.group(1)}")
                    return {
                        'task_id': task_id,
                        'benchmark': benchmark,
                        'category': cat_match.group(1),
                        'confidence': 1,
                        'reasoning': f'Extracted from truncated JSON: {content[:150]}',
                        'success': True,
                    }
                logger.warning(f"[{benchmark}/{task_id}] JSON parse error: {e}, content: {content[:100]}")
                if attempt == max_retries - 1:
                    return {
                        'task_id': task_id,
                        'benchmark': benchmark,
                        'category': 'U',
                        'confidence': 0,
                        'reasoning': f'Parse error: {content[:100]}',
                        'success': False,
                    }

        except Exception as e:
            logger.error(f"[{benchmark}/{task_id}] Error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return {
                    'task_id': task_id,
                    'benchmark': benchmark,
                    'category': 'U',
                    'confidence': 0,
                    'reasoning': str(e),
                    'success': False,
                }

    return {
        'task_id': task_id,
        'benchmark': benchmark,
        'category': 'U',
        'confidence': 0,
        'reasoning': 'Max retries exceeded',
        'success': False,
    }


def load_failure_cases(exp_dir: Path) -> list:
    """加载所有失败案例"""
    failure_dir = exp_dir / 'failure_cases'
    if not failure_dir.exists():
        logger.error(f"Failure cases directory not found: {failure_dir}")
        return []

    all_cases = []

    for f in failure_dir.glob('*_failed.json'):
        try:
            with open(f) as fp:
                data = json.load(fp)
                for case in data.get('failures', []):
                    case['benchmark'] = data.get('benchmark', f.stem.replace('_failed', ''))
                    all_cases.append(case)
        except Exception as e:
            logger.warning(f"Failed to load {f}: {e}")

    logger.info(f"Loaded {len(all_cases)} failure cases")
    return all_cases


def save_results(exp_dir: Path, results: list):
    """保存评估结果"""
    eval_dir = exp_dir / 'category_analysis'
    eval_dir.mkdir(parents=True, exist_ok=True)

    # 保存所有结果
    with open(eval_dir / 'category_results.json', 'w') as f:
        json.dump({
            'model': EVAL_MODEL,
            'total_evaluated': len(results),
            'successful': sum(1 for r in results if r.get('success')),
            'results': results,
        }, f, indent=2)

    # 按 category 统计
    from collections import Counter
    cat_counts = Counter(r.get('category', 'U') for r in results)

    # 保存统计
    stats = {
        'total': len(results),
        'by_category': dict(cat_counts),
        'percentages': {k: f"{v/len(results)*100:.1f}%" if len(results) > 0 else "0%"
                        for k, v in cat_counts.items()},
        'category_names': CATEGORIES,
    }

    with open(eval_dir / 'category_stats.json', 'w') as f:
        json.dump(stats, f, indent=2)

    # 生成可视化 HTML
    generate_category_dashboard(exp_dir, results, stats)

    logger.info(f"Results saved to {eval_dir}")

    return stats


def generate_category_dashboard(exp_dir: Path, results: list, stats: dict):
    """生成 category 可视化 HTML"""
    from collections import Counter

    eval_dir = exp_dir / 'category_analysis'
    cat_counts = Counter(r.get('category', 'U') for r in results)

    # 按 benchmark + category 统计
    bench_cat = {}
    for r in results:
        if r.get('success'):
            b = r.get('benchmark', 'unknown')
            c = r.get('category', 'U')
            if b not in bench_cat:
                bench_cat[b] = Counter()
            bench_cat[b][c] += 1

    # 类别颜色
    colors = {
        'A': '#f87171',  # red
        'B': '#fb923c',  # orange
        'C': '#fbbf24',  # yellow
        'D': '#4ade80',  # green
        'E': '#60a5fa',  # blue
        'U': '#94a3b8',  # gray
    }

    total = len(results)
    pie_data = ""
    bar_rows = ""

    for cat in ['A', 'B', 'C', 'D', 'E']:
        count = cat_counts.get(cat, 0)
        pct = count / total * 100 if total > 0 else 0
        pie_data += f"""{{ label: "{cat}: {CATEGORIES[cat]}", value: {count}, color: "{colors[cat]}" }},"""
        bar_rows += f"""
        <div style="margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                <span><strong>{cat}</strong>: {CATEGORIES[cat]}</span>
                <span>{count} ({pct:.1f}%)</span>
            </div>
            <div style="background: #334155; border-radius: 4px; height: 24px; overflow: hidden;">
                <div style="background: {colors[cat]}; height: 100%; width: {pct}%; display: flex; align-items: center; padding-left: 0.5rem; font-size: 0.75rem;">
                </div>
            </div>
        </div>"""

    # Benchmark table
    all_cats = ['A', 'B', 'C', 'D', 'E']
    bench_header = "<tr><th>Benchmark</th>" + "".join(f"<th>{c}</th>" for c in all_cats) + "<th>Total</th></tr>"
    bench_rows = ""
    for bench, counts in sorted(bench_cat.items()):
        bench_total = sum(counts.values())
        bench_rows += f"<tr><td>{bench}</td>"
        for c in all_cats:
            v = counts.get(c, 0)
            bench_rows += f"<td style='color: {colors[c] if v > 0 else '#64748b'}'>{v}</td>"
        bench_rows += f"<td><strong>{bench_total}</strong></td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Failure Category Analysis</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #f8fafc; margin-bottom: 0.5rem; }}
.subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-top: 2rem; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
.card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; }}
.card h2 {{ font-size: 1.1rem; color: #94a3b8; margin-bottom: 1rem; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 0.75rem; text-align: center; border-bottom: 1px solid #334155; }}
th {{ color: #94a3b8; font-size: 0.875rem; }}
td {{ font-size: 0.95rem; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
.sum-card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; text-align: center; }}
.sum-label {{ font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.5rem; }}
.sum-val {{ font-size: 1.75rem; font-weight: 700; }}
.tldr {{ background: #1e3a5f; border-left: 4px solid #60a5fa; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; }}
.tldr-label {{ font-size: 0.75rem; color: #60a5fa; font-weight: 700; margin-bottom: 0.25rem; }}
.tldr-text {{ font-size: 0.9rem; color: #bfdbfe; }}
</style>
</head>
<body>
<div class="container">
    <h1>🔍 Failure Category Analysis</h1>
    <p class="subtitle">Model: {EVAL_MODEL} | Experiment: {exp_dir.name}</p>

    <div class="tldr">
        <div class="tldr-label">TLDR</div>
        <div class="tldr-text">Analyzed {total} failure cases. Dominant categories: {', '.join(f"{c}({cat_counts.get(c,0)})" for c in ['A','B','C','D','E'] if cat_counts.get(c,0) > 0)}</div>
    </div>

    <div class="summary">
        <div class="sum-card">
            <div class="sum-label">Total Failures</div>
            <div class="sum-val">{total}</div>
        </div>
        <div class="sum-card">
            <div class="sum-label">Evaluated</div>
            <div class="sum-val">{sum(1 for r in results if r.get('success'))}</div>
        </div>
        <div class="sum-card">
            <div class="sum-label">Top Category</div>
            <div class="sum-val" style="color: #f87171;">{max(cat_counts, key=cat_counts.get) if cat_counts else 'N/A'}</div>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h2>Category Distribution</h2>
            {bar_rows}
        </div>
        <div class="card">
            <h2>Benchmark × Category</h2>
            <table>
                {bench_header}
                {bench_rows}
            </table>
        </div>
    </div>
</div>
</body>
</html>"""

    with open(eval_dir / 'category_dashboard.html', 'w') as f:
        f.write(html)

    logger.info(f"Category dashboard saved to {eval_dir / 'category_dashboard.html'}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate failure cases using LLM')
    parser.add_argument('--exp-dir', type=str, required=True, help='Experiment directory')
    parser.add_argument('--max-samples', type=int, default=0, help='Max samples to evaluate (0=all)')
    parser.add_argument('--threads', type=int, default=4, help='Parallel threads')
    parser.add_argument('--model', type=str, default=EVAL_MODEL, help='Evaluation model')

    args = parser.parse_args()

    exp_dir = Path(args.exp_dir)
    if not exp_dir.exists():
        logger.error(f"Experiment directory not found: {exp_dir}")
        sys.exit(1)

    logger.info(f"Evaluating failures in: {exp_dir}")
    logger.info(f"Model: {args.model}")

    # 加载失败案例
    cases = load_failure_cases(exp_dir)

    if not cases:
        logger.error("No failure cases found")
        sys.exit(1)

    if args.max_samples > 0:
        cases = cases[:args.max_samples]
        logger.info(f"Limited to {args.max_samples} samples")

    # 初始化 LLM client
    client = OpenAI(
        base_url=API_URL,
        api_key=API_KEY,
    )

    # 并行评估
    results = []
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(evaluate_single_failure, case, client): case
            for case in cases
        }

        for future in concurrent.futures.as_completed(futures):
            case = futures[future]
            try:
                result = future.result()
                results.append(result)
                completed += 1

                if completed % 10 == 0:
                    logger.info(f"Progress: {completed}/{len(cases)}")

            except Exception as e:
                logger.error(f"Error: {e}")
                results.append({
                    'task_id': case.get('task_id'),
                    'benchmark': case.get('benchmark'),
                    'category': 'U',
                    'confidence': 0,
                    'reasoning': str(e),
                    'success': False,
                })

    # 保存结果
    stats = save_results(exp_dir, results)

    # 打印统计
    print("\n" + "=" * 60)
    print("CATEGORY ANALYSIS COMPLETED")
    print("=" * 60)
    print(f"\nTotal failures: {stats['total']}")
    print("\nDistribution:")
    for cat in ['A', 'B', 'C', 'D', 'E']:
        if cat in stats['by_category']:
            pct = stats['percentages'][cat]
            print(f"  {cat} ({CATEGORIES[cat]}): {stats['by_category'][cat]} ({pct})")

    print(f"\nResults saved to: {exp_dir / 'category_analysis'}")
    print("=" * 60)


if __name__ == '__main__':
    main()
