# NanoBot Benchmark 项目进度

## 项目概述

使用统一的 NanoBot Agent 推理框架运行多个 benchmark 测评。

## 项目结构

```
work/nanopro/
├── nanobot/                    # NanoBot Agent 核心代码
├── benchmarks/                 # 测试仓库
│   ├── pinchbench/
│   ├── skillsbench/
│   └── agentbench-openclaw/
├── scripts/                    # 测试脚本
│   ├── agent/               # Agent 适配器 (nanobot.py)
│   ├── adapters/            # Benchmark 适配器
│   ├── run.py               # 统一入口
│   └── run_all_benchmarks.py # 运行所有 benchmark
├── docs/                      # 文档
│   ├── current_method.md
│   └── schedule.md
└── assets/                    # 资源文件
    ├── visualizations/       # HTML 可视化 dashboards
    ├── results/              # JSON 测试结果
    └── transcripts/          # 轨迹记录
```

## 已完成

### Recipe T1 — Memory (2026-03-27)
- [x] Memory 模块创建 (`src/harness/agent/memory/`)
  - `item.py`: MemoryItem dataclass
  - `store.py`: EpisodicMemoryStore
  - `policy.py`: WritePolicy, RetrievalPolicy enums
  - `config.py`: MemoryConfig dataclass
- [x] NanoBotAgent 集成 memory
  - `__init__`: 添加 memory_config 参数
  - `_run_loop()`: 迭代前检索 memory 并注入 prompt
  - `_execute_tool()`: 工具执行后根据 write policy 写入 memory
  - `execute()`: 任务结束时记录 memory summary 到 transcript
- [x] run.py CLI 参数
  - `--memory-enabled`: 启用 memory
  - `--memory-max-items`: 最大 items 数量 (默认 20)
  - `--memory-retrieval-max`: 每次检索最大 items (默认 5)
  - `--memory-write-policy`: 写入策略 (默认 tool_result_or_error)
  - `--memory-retrieval-policy`: 检索策略 (默认 recent)

### Recipe T2 — Single-agent control (2026-03-28)
- [x] Control 模块创建 (`src/harness/agent/control/`)
  - `__init__.py`: 模块导出
  - `config.py`: ControlConfig, PlanFirstConfig, ReplanConfig, RetryConfig, ReflectionConfig
  - `plan_first.py`: PlanFirst 模块 - 任务开始前生成执行计划
  - `replan.py`: ReplanTrigger 模块 - 检测需要重新规划的信号
  - `reflection.py`: FailureReflection 模块 - 失败后进行反思
  - `preflight.py`: PreflightCheck 模块 - 工具调用前检查
  - `retry.py`: RetryPolicy 模块 - 失败重试策略
- [x] NanoBotAgent 集成 control
  - `__init__`: 添加 control_config 参数，初始化各 control 模块
  - `_run_loop()`: 集成 plan-first, replan, preflight, retry, reflection
  - `execute()`: 任务结束时重置 control 状态，记录 control summary 到 transcript
- [x] run.py CLI 参数
  - `--control-enabled`: 启用 control 模块
  - `--plan-first-enabled`: 启用 plan-first
  - `--replan-enabled`: 启用 replan trigger
  - `--retry-enabled`: 启用 retry policy
  - `--reflection-enabled`: 启用 failure reflection
  - `--preflight-enabled`: 启用 preflight check

### Recipe T3 — Minimal Collaboration (2026-03-28)
- [x] Collaboration 模块创建 (`src/harness/agent/collaboration/`)
  - `__init__.py`: 模块导出
  - `config.py`: CollabConfig, HandoffPolicy, RoleDefinition
  - `event.py`: CollabEvent dataclass
  - `roles.py`: PlannerRole, ExecutorRole, VerifierRole
  - `handoff.py`: HandoffManager
- [x] NanoBotAgent 集成 collaboration
  - `__init__`: 添加 collab_config 参数，初始化 collaboration 模块
  - `_run_loop()`: 集成 planner 生成计划，executor 执行步骤
  - `execute()`: 任务结束时重置 collaboration 状态，记录 collab summary 到 transcript
- [x] run.py CLI 参数
  - `--collab-enabled`: 启用 collaboration 模块
  - `--collab-mode`: 模式选择 (planner_executor / executor_verifier)
  - `--collab-critique-frequency`: critique 频率 (on_error / every_step / never)
  - `--collab-max-handoffs`: 最大 handoff 次数
  - `--collab-handoff-trigger`: handoff 触发时机
  - `--collab-planner-model`: planner 使用的模型
  - `--collab-verifier-model`: verifier 使用的模型

### Recipe T4 — Procedural Support (2026-03-28)
- [x] Procedure 模块创建 (`src/harness/agent/procedure/`)
  - `__init__.py`: 模块导出
  - `config.py`: ProceduralConfig, SkillCard
  - `event.py`: ProceduralEvent dataclass
  - `store.py`: ProceduralStore - skill card 存储
  - `trigger.py`: ProceduralTrigger - 关键词匹配触发
  - `expander.py`: ProceduralExpander - 格式化 skill card 内容
- [x] NanoBotAgent 集成 procedural
  - `__init__`: 添加 procedural_config 参数，初始化 procedural 模块
  - `_run_loop()`: 每次 LLM 调用前检查 trigger，注入 expanded skill context
  - `execute()`: 任务结束时重置 procedural 状态，记录 procedural summary 到 transcript
- [x] run.py CLI 参数
  - `--procedural-enabled`: 启用 procedural 模块
  - `--procedural-cards-dir`: skill cards 目录路径
  - `--procedural-max-expansions`: 每次迭代最大展开数量
  - `--procedural-show-skill-list`: 显示 skill 列表
  - `--procedural-cache-triggers`: 缓存已触发的 skills

### Recipe T5 — Memory + Control (2026-03-28)
- [x] `--recipe-t5` 便捷 flag
  - 同时启用 `--memory-enabled --control-enabled --plan-first-enabled --replan-enabled --reflection-enabled`

### 核心功能
- [x] BaseAgent 抽象基类定义
- [x] NanoBotAgent 实现 (使用 litellm)
- [x] SkillsBenchAdapter (87 tasks)
- [x] PinchBenchAdapter (23 tasks)
- [x] OpenClawBenchAdapter (40 tasks)
- [x] ClawBenchOfficialAdapter (315 tasks, 34 domains)
- [x] 统一命令行入口 run.py
- [x] 并行执行支持 (--threads 参数)
- [x] 轨迹记录 (transcripts JSONL)

### 测试运行
- [x] 使用 openrouter/google/gemini-3-flash-preview 模型完成完整测试
- [x] SkillsBench: 73.41% (56/87) - 409s
- [x] PinchBench: 61.73% (14.2/23) - 364s
- [x] OpenClawBench: 62.05% (24.8/40) - 717s
- [x] TRIBE-INC/claw-bench: 已完成
- [x] skillbench: 已完成

### SciSkillBench 集成 (2026-03-26)
- [ ] SciSkillBench 适配器 - 因难以适配已放弃

### ClawBench Official 集成 (2026-03-24)
- [x] ClawBenchOfficialAdapter (315 tasks, 34 domains)
- [x] 支持级别筛选 (L1/L2/L3/L4/fast)
- [x] 支持领域筛选
- [x] 使用 pytest verifier 评分
- [x] 测试运行: 57.3% (156/315) - 597s

### 可视化
- [x] HTML Dashboard 生成 (benchmark_summary.html)
- [x] Chart.js 图表展示
- [x] 分 Tab 展示各 benchmark 详情

### 项目重构
- [x] 从 work/benchmarks 迁移到 work/nanopro
- [x] 目录结构整理
- [x] 路径引用更新

## 待完成

### 功能增强
- [ ] 支持更多 benchmark 适配器
- [ ] OpenClaw Agent 适配器实现
- [ ] 分布式运行支持

### 测试改进
- [ ] 多个模型对比测试
- [ ] 多次运行取平均值
- [ ] 错误分析报告

### 可视化增强
- [ ] 任务级别详细分析
- [ ] 轨迹回放功能
- [ ] 性能趋势图表

## 运行命令

```bash
cd /Volumes/F/Clauding/AwesomeSkill/work/nanopro/scripts

# 运行所有 benchmark
python run_all_benchmarks.py

# 运行特定 benchmark
python run.py --benchmark skillsbench --threads 10

# 查看可视化结果
open ../assets/visualizations/benchmark_summary.html
```

## 最新测试结果 (2026-03-26)

| Benchmark | Score | Passed/Total | Time | Status |
|-----------|-------|-------------|------|--------|
| ClawBench Official | 57.3% | 156/315 | 597s | ✅ |
| SkillsBench | 73.41% | 56/87 | 409s | ✅ |
| PinchBench | 61.73% | 14.2/23 | 364s | ✅ |
| OpenClawBench | 62.05% | 24.8/40 | 717s | ✅ |
| TRIBE-INC/claw-bench | - | - | - | ✅ |
| skillbench | - | - | - | ✅ |
| SciSkillBench | - | - | - | ❌ 放弃 |

**已完成**: skillsbench, TRIBE-INC/claw-bench, Pinchbench, AgentBench-OpenClaw, claw-bench, skillbench
**已放弃**: sciskillbench

**模型**: openrouter/google/gemini-3-flash-preview
