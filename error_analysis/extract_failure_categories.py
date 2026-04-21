#!/usr/bin/env python3
"""从 prompts_answered.json 文件中提取简化的 failure category 记录"""

import json
import re
from pathlib import Path

def extract_failure_category(llm_answer: str) -> str:
    """从 llm_answer 中提取 \boxed{X} 格式的 failure category"""
    match = re.search(r'\\boxed{([A-F])}', llm_answer)
    if match:
        return match.group(1)
    return "Unknown"

def process_file(filepath: str) -> list:
    """处理单个 JSON 文件，返回提取的记录列表"""
    records = []
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for item in data:
        bench = item.get('bench', '')
        task_id = item.get('task_id', '')
        llm_answer = item.get('llm_answer', '')
        failure_category = extract_failure_category(llm_answer)

        records.append({
            'bench': bench,
            'task_id': task_id,
            'failure_category': failure_category
        })

    return records

def main():
    base_dir = Path('/Volumes/F/Clauding/ClawEvalkit/error_analysis/outputs')

    files = [
        'agentbench_glm_prompts_answered.json',
        'clawbench_glm_prompts_answered.json',
        'claweval_glm_prompts_answered.json'
    ]

    all_records = []
    for filename in files:
        filepath = base_dir / filename
        if filepath.exists():
            records = process_file(filepath)
            all_records.extend(records)
            print(f"处理 {filename}: {len(records)} 条记录")
        else:
            print(f"文件不存在: {filepath}")

    # 按 failure_category 分组
    grouped = {}
    for record in all_records:
        cat = record['failure_category']
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            'bench': record['bench'],
            'task_id': record['task_id']
        })

    # 输出结果
    output = {
        'total_records': len(all_records),
        'by_category': grouped
    }

    output_path = base_dir / 'failure_categories_by_group.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n总计: {len(all_records)} 条记录")
    print(f"结果已保存到: {output_path}")

    # 打印每个 category 的统计
    for cat in sorted(grouped.keys()):
        print(f"  Category {cat}: {len(grouped[cat])} 条")

if __name__ == '__main__':
    main()
