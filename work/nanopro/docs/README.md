# 统一评估框架 (BenchEval)

使用统一的 Agent 推理框架运行多个 benchmark 的测评。

## 架构

```
benchmarks/
├── nanobot/                    # Agent 推理框架
├── pinchbench/                  # Benchmark 1
├── agentbench-openclaw/        # Benchmark 2
├── scikillbench/              # Benchmark 3
├── skillbench/                # Benchmark 4
├── skillsbench/               # Benchmark 5
├── claw-bench-tribe/          # Benchmark 6 (TRIBE-INC 版本)
├── claw-bench-official/        # Benchmark 7 (官方版本)
└── scripts/                    # 统一评估框架
    ├── run.py                  # 统一入口脚本
    ├── test_run.py            # 测试脚本
    ├── agent/                  # Agent 适配器
    │   ├── base.py            # 统一接口定义
    │   └── nanobot.py         # NanoBot 适配
    └── adapters/              # Benchmark 适配器
        └── pinchbench.py       # PinchBench 适配
```

## 快速开始

### 基本用法

```bash
cd /Volumes/F/Clauding/AwesomeSkill/work/benchmarks

# 运行 pinchbench (使用默认 API 配置)
python scripts/run.py \
    --benchmark pinchbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key <your-api-key> \
    --model gpt-4o-mini
```

### 测试脚本（使用 .env 配置）

```bash
# 设置环境变量
export API_URL=https://openrouter.ai/api/v1
export API_KEY=your-api-key

# 运行测试（5 个任务）
python scripts/test_run.py
```

## 支持的 Benchmark

| Benchmark | 状态 | 任务数 | 说明 |
|-----------|------|--------|------|
| pinchbench | ✅ 已实现 | 23 | OpenClaw agent 测试，支持 automated/llm/hybrid 评分 |
| agentbench-openclaw | 🔜 待实现 | 40 | 7 领域 |
| claw-bench-tribe | 🔜 待实现 | ~32 | clawdbot 测试 |
| claw-bench-official | 🔜 待实现 | 313 | 32 领域，4 难度级别 |
| scikillbench | 🔜 待实现 | - | 材料科学多智能体 |
| skillbench | 🔜 待实现 | - | SWE-bench 风格 |
| skillsbench | 🔜 待实现 | - | agent skills 评估 |

## 当前测试结果 (gpt-4o-mini)

```
Overall Score: 65.2%
- task_00_sanity: 100%  ✅
- task_01_calendar: 83%  ✅
- task_04_weather: 86%   ✅
- task_08_memory: 0%      ❌ (需要 notes.md)
- task_09_files: 57%      ⚠️
```

## 添加新的 Benchmark

1. 在 `scripts/adapters/` 下创建新的适配器
2. 实现 `BaseAdapter` 接口
3. 在 `scripts/run.py` 中注册

## 设计要点

### 1. Agent 接口 (BaseAgent)

定义统一的 Agent 接口：
- `execute(prompt, session_id)`: 单轮对话
- `execute_multi(prompts, session_id)`: 多轮对话

### 2. Benchmark 适配器

每个 Benchmark 有自己的适配器，负责：
- 加载任务（从 tasks/ 目录）
- 解析任务格式（YAML frontmatter）
- 执行 grading 代码评分
- 生成报告

### 3. PinchBench 适配器特点

- 支持 3 种评分方式：automated（自动）、llm_judge（LLM 评分）、hybrid（混合）
- 自动执行 grading 代码
- 支持多次运行取平均
- 输出 JSON 格式结果

## 输出格式

```json
{
  "benchmark": "pinchbench",
  "timestamp": 1679500000,
  "overall_score": 65.2,
  "total_tasks": 5,
  "category_scores": {
    "CALENDAR": {"score": 83.0, "count": 1},
    "WEATHER": {"score": 86.0, "count": 1}
  },
  "task_scores": {
    "task_00_sanity": {"task_name": "Sanity Check", "mean": 1.0, "std": 0.0},
    "task_01_calendar": {"task_name": "Calendar Event Creation", "mean": 0.83, "std": 0.0}
  }
}
```
