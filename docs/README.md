# exp88_AwesomeSkill — ClawEvalKit 对接文档

## 项目概述

ClawEvalKit 是一个统一的 Agent 评测框架，整合了 8 个不同的 benchmark，采用 VLMEvalKit 风格的单入口 `run.py` + OpenCompass 风格的 YAML 模型配置。

**核心特性**:
- 8 个 benchmark 全部使用 NanoBotAgent 作为统一推理引擎
- YAML 配置驱动，支持 OpenRouter / ARK / 自定义 API
- 单命令运行: `python3 run.py --bench tribe --model seed-1.8`
- 结果自动缓存和汇总

## 仓库结构

```
ClawEvalKit/
├── run.py                          # 统一入口 (100 行)
├── clawevalkit/                    # 核心包
│   ├── config.py                   # YAML 配置加载
│   ├── inference.py                # 评测调度器
│   ├── summarizer.py               # 结果汇总 + 表格打印
│   ├── dataset/                    # 8 个 Benchmark 实现
│   │   ├── base.py                 # BaseBenchmark ABC (60 行)
│   │   ├── tribe.py                # 8 纯 LLM 测试 (119 行)
│   │   ├── pinchbench.py           # 23 规则评分任务 (210 行)
│   │   ├── agentbench.py           # 40 L0+L1 评分 (146 行)
│   │   ├── skillbench.py           # 22 harness+pytest (69 行)
│   │   ├── skillsbench.py          # 56+ 多轮代码生成 (236 行)
│   │   ├── zclawbench.py           # 18 NanoBotAgent+Judge (145 行)
│   │   ├── wildclawbench.py        # 10 安全对齐 (118 行)
│   │   └── clawbench_official.py   # 250 ReAct+Pytest (97 行)
│   └── utils/
│       ├── nanobot.py              # 共享 NanoBotAgent 导入 (50 行)
│       ├── api.py                  # call_llm() 裸 API (57 行)
│       └── env.py                  # 环境变量加载 (32 行)
├── configs/models/                 # YAML 模型配置
│   ├── openrouter.yaml             # Claude/Gemini via OpenRouter
│   └── seed.yaml                   # ByteDance Seed 1.8 (内部)
├── OpenClawPro/                    # Agent 执行框架 (git submodule)
│   └── harness/agent/nanobot.py    # NanoBotAgent 核心
├── benchmarks/                     # 评测数据 (7 个子目录)
├── outputs/                        # 评测结果 (gitignored)
└── tests/                          # 13 个测试
```

**代码规模**: 1,480 行 Python (核心包 + 入口)

## 8 个 Benchmark 概览

| Key | Benchmark | 任务数 | 评分范围 | 推理引擎 | 评分方式 |
|-----|-----------|--------|---------|----------|---------|
| `tribe` | Claw-Bench-Tribe | 8 | 0-100 | NanoBotAgent | 规则匹配 (lambda) |
| `pinchbench` | PinchBench | 23 | 0-100 | NanoBotAgent | 内嵌 grade() 函数 |
| `agentbench` | AgentBench-OpenClaw | 40 | 0-100 | NanoBotAgent CLI | L0 规则 + L1 指标 |
| `skillbench` | SkillBench | 22 | 0-100% | NanoBotAgent adapter | harness + pytest |
| `skillsbench` | SkillsBench | 56+ | 0-100% | NanoBotAgent | 多轮 + pytest |
| `zclawbench` | ZClawBench Subset | 18 | 0-1 | NanoBotAgent | LLM Judge |
| `wildclawbench` | WildClawBench | 10 | 0-1 | NanoBotAgent | LLM Judge |
| `clawbench-official` | ClawBench Official | 250 | 0-100 | OpenClawAdapter | ReAct + Pytest |

## 已跑通的评测结果

### Tribe Benchmark (8 tasks, 纯 LLM 推理)

| Model | Score | Passed | Total | 备注 |
|-------|-------|--------|-------|------|
| **Seed 1.8** | **100.0** | 8/8 | 8 | ARK API, 全部通过 |
| Claude Sonnet 4.6 | 25.0 | 2/8 | 8 | OpenRouter key 额度用尽 |

### 历史 Benchmark 数据 (来自 nanopro artifacts)

以下是此前在 OpenClawPro/nanopro 阶段跑出的结果（多个模型×多个 benchmark）:

**AgentBench-OpenClaw** (40 tasks):
- Claude Opus 4.6: 68.2
- Claude Sonnet 4.6: 69.2
- Gemini 2.5 Pro: 63.6

**PinchBench** (23 tasks):
- Claude Opus (official): 86.3
- Claude Sonnet (official): 86.9
- Gemini 2.5 Pro (official): 61.4
- GPT-4o (official): 64.7

**ZClawBench** (18 tasks):
- Seed 1.6: 0.796 (最高)
- Seed 1.8: 0.476

**WildClawBench** (10 tasks):
- Seed 1.8: 0.735 (最高)

## 关键技术决策

### NanoBotAgent 统一推理引擎

**决策**: 所有 benchmark 统一使用 NanoBotAgent 作为推理引擎，而非各自调用裸 API 或外部 subprocess。

**原因**:
1. 一致性 — 所有 benchmark 共享相同的 tool 能力 (ReadFile, WriteFile, EditFile, Exec, WebSearch, WebFetch)
2. 可维护性 — 修改推理逻辑只需改 NanoBotAgent 一处
3. 可复现性 — 相同的 agent 行为保证评测结果可比

**实现**: `clawevalkit/utils/nanobot.py` 提供共享的 `import_nanobot_agent()` 函数，按优先级搜索: pip 包 → `OPENCLAWPRO_DIR` 环境变量 → 仓库子目录。

### 评分与推理解耦

**决策**: 评分逻辑由各 benchmark 自行实现，NanoBotAgent 只负责执行。

**例子**:
- `tribe.py`: lambda 函数检查回复中是否包含正确答案
- `pinchbench.py`: exec() 执行 task markdown 中内嵌的 `grade()` 函数
- `skillsbench.py`: 外部 pytest 验证
- `zclawbench.py` / `wildclawbench.py`: LLM Judge 打分

## 环境配置

```bash
# 安装
pip install -e .

# 配置 API Key (.env 文件)
OPENROUTER_API_KEY=sk-or-v1-xxx      # Claude/Gemini via OpenRouter
ARK_API_KEY=xxx                       # ByteDance Seed 1.8

# 运行
python3 run.py --bench tribe --model seed-1.8
python3 run.py --summary
```

## 实验推进历程

### Round 1: 架构设计与基础搭建 (2026-03-18 ~ 03-29)

**设计动机**: 需要一个类 VLMEvalKit 的统一评测框架来管理 OpenClawPro 生态的多个 benchmark，避免每个 benchmark 各写一套推理+评分代码。

**具体方案**:
- 设计了 BaseBenchmark ABC，定义 `evaluate()` + `collect()` 接口
- YAML 配置驱动模型定义，支持 OpenRouter / 自定义 API
- 单入口 `run.py` 调度所有评测
- 8 个 benchmark 分别实现为独立的 dataset class

**结果**: 框架搭建完成，8 个 benchmark 全部注册。但推理引擎不统一：
- 4 个用 NanoBotAgent (zclawbench, wildclawbench, agentbench, clawbench-official)
- 2 个用裸 `call_llm()` (tribe, skillsbench)
- 1 个用外部 subprocess (pinchbench)
- 1 个用 ark_adapter diff patch (skillbench)

**核心发现**: 推理引擎不统一导致评测结果不可比较（不同的 tool 能力、不同的 prompt 格式）。

**下一步洞察**: 需要将所有 benchmark 统一到 NanoBotAgent 引擎。

---

### Round 2: Bug 修复与适配器完善 (2026-03-29 ~ 03-30)

**设计动机**: 初始版本在实际运行中遇到多个 bug，需要逐一修复才能跑通。

**具体方案**:
- 修复 skillbench 和 openclawbench 的 4 个 bug
- skillsbench 添加 `/root/` → workspace 路径重映射
- wildclawbench 符号链接清理
- NanoBotAgent 的 AgentResult 增加初始 prompt 记录

**结果**: 10 个 bug fix commit，基础框架稳定可用。

**核心发现**: 路径问题是 benchmark 适配最常见的坑 — 原始数据中硬编码 `/root/`、`/app/` 等路径需要重映射到实际 workspace。

---

### Round 3: 开源清理 (2026-03-31)

**设计动机**: 准备将仓库开源发布，需要清理所有内部资源（Seed/ARK/ByteDance 相关内容）。

**具体方案**:
- 创建 `bytedance_branch_guide.md`，记录内部 branch 与开源 branch 的差异
- `.gitignore` 添加 `configs/models/seed.yaml` 和 `.env`
- README.md 只暴露 OpenRouter 模型

**结果**: 仓库推送到 GitHub，外部用户可以开箱即用。内部用户通过 `seed.yaml` 和 `.env` 使用内部 API。

---

### Round 4: NanoBotAgent 统一推理引擎 (2026-04-01)

**设计动机**: Round 1 遗留的核心问题 — 4 个 benchmark 使用不同的推理引擎，需要统一到 NanoBotAgent。

**具体方案**:

| Benchmark | 改动前 | 改动后 |
|-----------|--------|--------|
| tribe | `call_llm()` 裸 API | `NanoBotAgent.execute().content` |
| skillsbench | 手动 regex 提取代码 + subprocess | NanoBotAgent 自主文件操作 + 外部 pytest |
| skillbench | ark_adapter diff patch | nanobot_adapter 直接修改文件 |
| pinchbench | subprocess 调外部 benchmark.py | 自主解析 task markdown + NanoBotAgent + exec(grade) |

**关键代码变化**:

1. **新建 `clawevalkit/utils/nanobot.py`**: 从 zclawbench/wildclawbench 中提取重复的 `_import_nanobot_agent()`
2. **tribe.py**: 创建一个 NanoBotAgent 实例，复用跑 8 个 test
3. **skillsbench.py**: 删除 `_call_llm_multi()`, `_extract_files()`, `_write_files()`, `_execute_scripts()`，改为 NanoBotAgent 自主操作
4. **pinchbench.py**: 完全重写，新增 `_load_tasks()` 解析 task markdown, `_run_grade()` exec 内嵌评分代码
5. **skillbench.py**: `--agent-cmd` 改为 nanobot_adapter
6. **新建 `benchmarks/skillbench/harness/agents/nanobot_adapter.py`**: NanoBotAgent 直接在 repo 中 ReadFile→EditFile

**修复的 bug**:
- `OpenClawPro/harness/agent/nanobot.py`: ExecTool() 接收了不支持的 `workspace` 参数，导致 TypeError

**结果**:
- Seed 1.8 跑 Tribe: **100.0 分 (8/8)** ✅
- 所有 8 个 benchmark class 导入正确
- 所有文件语法检查通过
- commit 并推送: `4e46d9a feat: unify all benchmarks to use NanoBotAgent as inference engine`

**核心发现**: NanoBotAgent 的内置 tools (ReadFile, WriteFile, EditFile, Exec) 可以完全替代 skillsbench 之前的手动 regex 提取 + subprocess 执行流程，代码更简洁、更鲁棒。

**下一步洞察**: 可以用更多模型×benchmark 组合跑全量评测，填充评测矩阵。

## 未来计划

- [ ] 用 Seed 1.8 跑全部 8 个 benchmark 的全量评测
- [ ] OpenRouter key 充值后，补充 Claude/Gemini 的评测数据
- [ ] SkillsBench 依赖问题修复（部分 task 需要特定 Python 包）
- [ ] CI/CD: GitHub Actions 自动化测试
- [ ] 支持并行评测（多任务并发）
