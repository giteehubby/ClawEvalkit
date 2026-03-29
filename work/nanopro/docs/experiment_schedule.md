# OpenClaw Paper Experiment Schedule
## Execution Guide, TODOs, Milestones, and Update Log for Claude Code

---

## 0. 本文档目的

本文档用于指导 Claude Code 执行整个项目，并在执行过程中持续更新。

本文件的作用不是讲论文故事，而是作为：

- 实验执行清单
- 里程碑管理表
- TODO 跟踪表
- 风险与阻塞记录表
- 每轮实验观察 memo 的承载处

Claude Code 在项目推进过程中必须持续更新本文件，包括：

- 已完成事项
- 当前进行中事项
- 下一步计划
- 实验结果摘要
- 风险与阻塞
- 决策变更记录

---

## 1. 总体执行原则

### 1.1 项目优先级

必须按以下优先级推进：

1. 建立统一、可复现的 harness
2. 固定 benchmark versions / task splits / configs
3. 跑通 Base OpenClaw baselines
4. 建立 failure pool 与 taxonomy rubric
5. 实现与筛选 training-free recipes
6. 冻结 best train-free setup
7. 运行 small-data SFT
8. 做 focused appendix probes
9. 输出 paper-ready results / figures / tables

### 1.2 绝对约束

Claude Code 必须遵守：

- 不允许先在 test 上选 recipe
- 不允许 benchmark 版本漂移
- 不允许缺日志运行
- 不允许把实验结果只保存在临时 notebook 或 terminal 输出里
- 不允许主文与附录实验边界混乱
- 不允许 procedural support / skill orchestration 重新夺回主轴

### 1.3 默认研究路径

默认路径必须是：

Base → Taxonomy → Train-free → Best Train-free → SFT → Appendix Probes

---

## 2. 当前阶段总览

### 项目状态
- Status: NOT STARTED

### 当前主目标
- 搭建统一评测与日志框架
- 明确 benchmark 接入顺序
- 跑通 Base OpenClaw 初始 baseline
- 为 failure taxonomy 建立数据基础

### 当前不做的事
- 不做 RL
- 不做复杂 multi-agent 结构搜索
- 不做大规模 orchestration 全因子实验
- 不做未固定版本的 benchmark sweep
- 不在 test 上调参

---

## 3. 目录与工程组织

### 3.1 项目目录结构

```
nanopro/
├── configs/               # 配置文件
│   ├── benchmarks/       # Benchmark 配置
│   ├── conditions/       # Condition 配置（training-free recipes）
│   └── experiments/      # 实验配置
├── src/                  # 源代码
│   ├── harness/          # Agent harness（NanoBot）
│   ├── runners/          # Benchmark runners
│   ├── conditions/       # Training-free recipe 实现
│   ├── logging/           # 日志工具
│   ├── analysis/          # 分析工具
│   ├── annotation/        # 标注工具
│   └── training/          # SFT 训练工具
├── artifacts/            # 实验输出
│   ├── runs/             # 原始运行结果 & transcripts
│   ├── aggregates/       # 聚合结果
│   ├── plots/            # 可视化图表
│   ├── tables/           # 结果表格
│   └── failure_cases/    # 失败案例分析
├── docs/                 # 文档
│   ├── paper_plan.md
│   ├── experiment_schedule.md
│   ├── schedule.md
│   ├── taxonomy_rubric.md
│   └── methods_notes.md
├── scripts/              # 实用脚本
└── benchmarks/           # Benchmark 仓库
```

### 3.2 TODO
- [x] 创建统一项目目录结构
- [x] 创建 README
- [ ] 创建统一 config schema
- [ ] 创建统一 run manifest schema
- [ ] 创建统一 results table schema
- [ ] 创建统一 trace metadata schema

### 3.3 完成判定
完成标准：
- 所有实验输出都能落盘到规范目录
- 任一 run 可以通过 manifest 被追踪
- 任何结果表都可以追溯到 source run ids

---

## 4. 统一配置系统 TODO

### 4.1 每个 run config 至少包含

- experiment_id
- benchmark_name
- benchmark_version / commit
- task_split / subset
- condition_name
- condition_version
- model_name
- model_version
- temperature
- max_steps
- tool_permission_set
- seed
- workspace_reset_policy
- logging_path
- output_path
- cost_accounting_flags

### 4.2 针对 training-free condition 的额外字段

#### Memory
- enabled
- write_policy
- read_policy
- max_items
- retrieval_budget

#### Single-agent control
- plan_first
- replan_frequency
- retry_budget
- reflection_trigger
- verifier_enabled
- tool_preflight_enabled

#### Minimal collaboration
- mode
- role_definitions
- handoff_policy
- critique_frequency

#### Procedural support（可选）
- enabled
- representation_type
- trigger_policy
- expansion_budget

### 4.3 针对 SFT 的额外字段
- train_dataset_id
- train_size
- val_dataset_id
- sft_method
- lora_rank / adapter settings
- epochs
- lr
- batch_size
- checkpoint_path

### 4.4 TODO
- [ ] 设计 config schema
- [ ] 实现 config validation
- [ ] 支持 config hashing / run fingerprint
- [ ] 支持 condition versioning
- [ ] 支持 manifest export

---

## 5. 日志与结果保存 TODO

### 5.1 每个 task run 必须保存

- task metadata
- benchmark metadata
- condition metadata
- model metadata
- final score
- normalized score（若适用）
- success / fail
- stop reason
- total prompt tokens
- extra prompt tokens
- tool calls
- steps
- runtime / latency
- trace path
- artifacts path
- error summary
- failure evidence snippet（如失败）
- optional predicted failure category（后处理阶段）

### 5.2 每个 step / interaction 建议保存
- step index
- agent thought summary（若可记录）
- tool chosen
- tool arguments
- tool result summary
- reflection / verification event
- memory read / write event
- collaboration handoff event
- procedural support retrieval / expansion event

### 5.3 TODO
- [ ] 统一 task-level result schema
- [ ] 统一 step-level event schema
- [ ] 统一 error logging schema
- [ ] 统一 artifact registry schema
- [ ] 确保 trace 可用于 failure analysis

---

## 6. Benchmark 接入计划

### 6.1 benchmark 接入顺序（建议严格按此顺序）

#### Priority 1 ✅ 已完成
- AgentBench-OpenClaw ✅
- official Claw Bench（lightweight quick subset）✅

#### Priority 2 ✅ 已完成
- PinchBench ✅

#### Priority 3 ❌ 已放弃
- ~~SciSkillBench~~ — 因难以适配，已放弃

#### Priority 4 ✅ 已完成
- SkillsBench ✅
- TRIBE-INC/claw-bench ✅

### 6.2 每个 benchmark runner 必须输出
- benchmark version / commit
- task ids
- scoring implementation version
- run manifest link
- per-task result rows
- trace locations

### 6.3 Benchmark 完成状态
| Benchmark | Status | Notes |
|-----------|--------|-------|
| AgentBench-OpenClaw | ✅ 完成 | |
| claw-bench (official) | ✅ 完成 | |
| PinchBench | ✅ 完成 | |
| SkillsBench | ✅ 完成 | |
| TRIBE-INC/claw-bench | ✅ 完成 | |
| skillbench | ✅ 完成 | |
| SciSkillBench | ❌ 放弃 | 难以适配 |

### 6.4 风险提示
- benchmark README 中任务数可能漂移，必须以固定版本和 task list 为准
- 有的 benchmark scoring 依赖外部环境，需提前锁定
- 必须避免 runner 逻辑差异影响 condition 对比

---

## 7. Base OpenClaw 基线阶段

### 7.1 阶段目标
在所有主 benchmark 上，跑通稳定的 Base OpenClaw baseline，作为后续一切 paired comparison 的 anchor。

### 7.2 交付物
- ✅ Base baseline per benchmark (5/5 benchmarks)
- ✅ 成本统计 (见 Dashboard)
- ✅ 失败任务池 (250 tasks)
- ✅ 原始 trace 与 artifacts (artifacts/runs/results/)
- ✅ 初始 failure evidence 导出 (baseline_summary.json)
- ✅ HTML 可视化 Dashboard (baseline_dashboard.html)

### 7.3 TODO
- [x] 跑通单 benchmark smoke test
- [x] 跑通 Base OpenClaw on AgentBench-OpenClaw (64.2%, 40 tasks)
- [x] 跑通 Base OpenClaw on official Claw Bench (54.8%, 151/315)
- [x] 跑通 Base OpenClaw on PinchBench (57.7%, 17/23)
- [x] 跑通 Base OpenClaw on SkillsBench (69.0%, 46/87)
- [x] 跑通 Base OpenClaw on TRIBE-INC/claw-bench (90.9%, 30/33)
- [x] 跑通 Base OpenClaw on skillbench
- [ ] ~~跑通 Base OpenClaw on SciSkillBench~~ — 已放弃
- [x] 导出统一 baseline summary table
- [x] 导出失败 run 列表与 evidence links
- [x] 生成 HTML 可视化 Dashboard

### 7.4 Base Baseline Results (2026-03-27)

**Model**: `google/gemini-3-flash-preview` (OpenRouter)

**Latest Re-run Results (with valid transcripts):**

| Benchmark | Score | Passed | Total | Difficulty |
|-----------|-------|--------|-------|------------|
| TRIBE-INC/claw-bench | 90.9% | 30 | 33 | Easy |
| SkillsBench | 70.1% | 52 | 87 | Medium |
| OpenClawBench | 58.2% | 40 | 40 | Medium |
| PinchBench | 62.0% | 23 | 23 | Medium |
| clawbench-official | 53.0% | 139 | 315 | Hard |
| skillbench | 36.4% | 8 | 22 | Medium |

**Overall**: 292/520 tasks passed (56.2%)

**Transcript Status**:
- 491 valid transcripts (non-empty)
- 7 empty transcripts (memory-related tasks in skillsbench)
- claw-bench-tribe re-run failed with JSON parsing error; using old successful run

**Results Location**: `artifacts/runs/results/`

**Failed Task Pool**: 228 tasks across 6 benchmarks available for failure taxonomy analysis.

### 7.4 完成判定
- 所有主 benchmark 至少有一版稳定 baseline
- 至少能生成统一 baseline 表
- 至少能抽样查看失败 run 的 trace

---

## 8. Failure Taxonomy 阶段

### 8.1 阶段目标
建立 failure taxonomy 的标注流程、rubric 和人工核验子集。

### 8.2 子阶段

#### Stage A — Pilot review
目标：
- 人工阅读 40–60 个失败样本
- 形成初版 A–E rubric
- 检查 taxonomy 是否需要微调

#### Stage B — Rubric freeze
目标：
- 冻结 dominant label 定义
- 冻结 evidence requirement
- 冻结 annotation template

#### Stage C — Formal annotation
目标：
- 抽 150–200 个失败样本双人标注
- 计算一致性
- 生成 category prevalence 表

### 8.3 标注输出格式（建议）
每条记录至少包括：
- benchmark
- task_id
- condition_name
- result_id / trace_id
- dominant_category
- evidence_snippet
- annotator_id
- confidence
- note

### 8.4 TODO
- [x] 建立 failure sample export script
- [x] 创建 taxonomy_rubric.md
- [ ] 完成 40–60 个 pilot failures 的人工阅读
- [ ] 冻结 taxonomy A–E
- [ ] 准备 formal annotation sheet
- [ ] 完成双人标注
- [ ] 计算 agreement
- [ ] 导出 prevalence tables

### 8.5 风险提示
- taxonomy 过宽会失去解释力
- taxonomy 过细会降低一致性
- 必须保持 dominant label 机制，否则后续 CRR 分析会混乱

---

## 9. Training-free Recipes 实现阶段

### 9.1 总体原则
实现 training-free recipes 时，必须优先保证：

- 简洁
- 可解释
- 可配置
- 可 ablate
- 可记录事件
- 可独立启用/关闭

不追求复杂 fancy 设计。

### 9.1.1 T5 (Memory+Control) 选定为 Best Combined Train-free

**设计决策**：选择 T5 (Memory+Control) 而非 T3 (+Collab) 作为 best combined train-free：

| Criterion | T5 (Memory+Control) | T3 (+Collab) |
|-----------|---------------------|--------------|
| NIR | 较低 | 最低 (0.5%) |
| CRR_A | 好 | 仅覆盖 D 类 |
| CRR_C | 好 | - |
| 成本 | +0.03/task | +0.08/task |
| Dev delta | +9.1pp (最优) | 较低 |

> 参考师兄 EMNLP 2027 投稿的 Dev selection 结果。

---

### 9.2 Recipe T1 — Memory

#### 目标
缓解 C 类 failures，并部分帮助 D 类 failures。

#### 最小要求
- task-local episodic memory
- memory write events
- memory read events
- retrieval budget
- 可追踪 memory item 来源与用途

#### TODO
- [ ] 定义 memory item schema
- [ ] 实现 write policy
- [ ] 实现 retrieval policy
- [ ] 实现 memory event logging
- [ ] 验证 memory 不会引入明显 prompt 爆炸
- [ ] 在 dev 上跑 smoke ablation

---

### 9.3 Recipe T2 — Single-agent control recipe

#### 目标
缓解 A/B/D 类 failures。

#### 推荐最小组件
- plan-first
- bounded replanning
- failure-triggered reflection
- tool preflight check
- bounded retries

#### TODO
- [ ] 定义控制 recipe config
- [ ] 实现 plan-first 模块
- [ ] 实现 replan trigger
- [ ] 实现 failure-triggered reflection
- [ ] 实现 preflight / retry policy
- [ ] 记录控制事件日志
- [ ] 在 dev 上跑 smoke ablation

---

### 9.4 Recipe T3 — Minimal collaboration

#### 目标
缓解 A/D 类 failures。

#### 约束
- 只实现一种最小二角色配置
- 优先选择 planner-executor 或 executor-verifier 之一
- 不做复杂多 agent 群体

#### TODO
- [x] 选定 collaboration mode
- [x] 定义角色职责
- [x] 实现 handoff protocol
- [x] 实现 collaboration event logging
- [x] 在 dev 上跑 smoke ablation
- [ ] 比较 collaboration 的额外成本

#### 当前实现状态
- Chosen mode: `planner_executor`
- Scope intentionally frozen to one minimal two-role path; `executor_verifier` not yet hardened
- Planner generates an initial plan before the first main-agent iteration
- On tool execution error, executor can hand off back to planner for bounded plan revision (`max_handoffs`)
- Collaboration events are written into transcript and summarized at task end
- Planner / verifier model overrides are now respected by role-local LLM calls

#### Smoke 验证
- Date: 2026-03-28
- Benchmark: `pinchbench`
- Task subset: `task_00_sanity`
- Model: `openrouter/google/gemini-3-flash-preview`
- Result: startup + transcript logging passed, score `100.0% (1/1)`
- Transcript contains `plan_generated` and `collab_summary` events
- Additional smoke: `task_01_calendar`, score `83.3% (0.8333/1)`, confirmed planner + tool-use path works on a real file-writing task
- Observed behavior on `task_01_calendar`: planner generated a 6-step plan; final run completed via direct `write_file` without triggering a revision handoff
- Additional smoke: `task_19_spreadsheet_summary`, score `0.0%`, but confirmed real revision behavior under repeated tool failures
- Observed behavior on `task_19_spreadsheet_summary`: planner generated an initial plan, repeated `exec` failures triggered bounded planner handoffs, and transcript summary recorded `plan_generated: 4` plus `handoff: 3` with `total_handoffs: 3`

#### 正式实验结果
- Date: 2026-03-29
- Model: `openrouter/google/gemini-3-flash-preview`
- Results location: `work/nanopro/artifacts/runs/results/t3_collaboration/`
- `skillsbench`: `74.31% (58/87)`
- `pinchbench`: `78.84% (23 tasks)`
- `openclawbench`: `71.89% (40 tasks)`
- `clawbench_official`: `60.01% (180/315)`
- `skillbench`: `95.45% (21/22)`
- `claw-bench-tribe`: skipped for now due to known benchmark bug per team instruction

#### Base vs T3 对照
- Baseline reference: use the "Latest Re-run Results" in Section 7.4 to keep one comparison baseline

| Benchmark | Base | T3 | Delta |
|-----------|------|----|-------|
| SkillsBench | 70.1% | 74.31% | +4.21pp |
| PinchBench | 62.0% | 78.84% | +16.84pp |
| OpenClawBench | 58.2% | 71.89% | +13.69pp |
| clawbench-official | 53.0% | 60.01% | +7.01pp |
| skillbench | 36.4% | 95.45% | +59.05pp |

- Note: `skillbench` has an older `50.0% (11/22)` baseline record elsewhere in this document; the table above uses the newer re-run baseline from Section 7.4 for consistency
- Note: `claw-bench-tribe` is excluded from the comparison because the benchmark is currently skipped due to a known bug

#### 当前已知问题 / 后续
- Need a richer smoke case that exercises tool calls and ideally triggers a real revision handoff
- `claw-bench-tribe` remains skipped per current team instruction

---

### 9.5 Recipe T4 — Procedural support（可选但推荐）

#### 目标
聚焦 E 类 failures。

#### 推荐内容
- structured skill / procedure card
- compact procedural support
- on-demand expansion
- lightweight trigger policy

#### 约束
- 不做全篇方法论文式大 sweep
- 不做过多 selector 变量
- 只做可解释、低自由度变体

#### TODO
- [ ] 定义 procedural support schema
- [ ] 实现 compact representation
- [ ] 实现 trigger / expansion policy
- [ ] 实现 logging
- [ ] 在 skill-heavy benchmark 上跑 focused ablation

---

## 10. Dev 筛选阶段

### 10.1 阶段目标
在 dev split 上识别：

- 最稳的 single training-free recipe
- 最优的 combined training-free recipe
- 是否保留 procedural support 进入主文

### 10.2 比较条件（建议最少）
- Base
- +Memory
- +Single-agent control
- +Minimal collaboration
- +Procedural support（focused）
- +若干合理组合

### 10.3 决策标准
优先看：

1. paired delta
2. negative interference
3. added cost
4. per-category repair plausibility
5. implementation simplicity / stability

### 10.4 TODO
- [ ] 切分 dev / test
- [ ] 定义 dev 筛选表格模板
- [ ] 跑完主要 training-free 条件的 dev 结果
- [ ] 写出 dev observations memo
- [ ] 选定 best single recipe
- [ ] 选定 best combined train-free recipe
- [ ] 冻结进入 test 的条件集合

---

## 11. Main Test Evaluation 阶段

### 11.1 阶段目标
在 test split 上正式评估主结果。

### 11.2 正式条件（建议）
- Base
- Best single training-free recipe
- Best combined train-free recipe

若预算足够，可增加：
- focused procedural support condition

### 11.3 输出
- benchmark 内 paired delta
- 95% CI
- NIR
- added cost
- per-category repair rate
- case study candidates

### 11.4 TODO
- [ ] 冻结 test configs
- [ ] 运行所有主 benchmark test
- [ ] 聚合 benchmark-level results
- [ ] 生成主结果表
- [ ] 生成 cost-benefit plot
- [ ] 生成 category repair plot
- [ ] 生成 negative interference plot

---

## 12. Small-data SFT 阶段

### 12.1 阶段目标
回答：
- SFT 相比 best train-free 多修了什么？
- SFT 的数据效率如何？
- train-free 与 SFT 是替代还是互补？

### 12.1.1 SFT 的定位（基于师兄 EMNLP 2027 投稿）

**互补关系，非替代**：
- Train-free recipes 可修复 A-D 类 28-45% 失败（成本接近零）
- SFT 在 E 类（程序性知识）上有 **1.73×** 优势
- 但 SFT 的 NIR 高出 train-free 10 倍

**Mock CRR 数据（待真实数据替换）**：
| Category | Train-free Best | SFT-1000 |
|----------|-----------------|----------|
| A | 0.38 | 更高 |
| B | <0.21 | 0.21 |
| C | 0.42 | 更高 |
| D | 0.45 | 更高 |
| E | 0.11-0.12 | **0.19 (1.73×)** |

**不评估 T5 + SFT 组合**：因为 T5 已占很低 NIR budget，额外 SFT 的 NIR 会叠加。

### 12.2 训练设置原则
- 首选 LoRA-SFT / adapter-SFT
- 严格 train / dev / test 分离
- 尽量平衡 A–E 类别
- 优先 corrected trajectories / tool-using demonstrations

### 12.3 建议训练规模
优先：
- 100
- 300
- 1000

预算紧张时：
- 50
- 200
- 500

### 12.4 TODO
- [ ] 定义 SFT 数据 schema
- [ ] 构建训练样本收集管线
- [ ] 标记样本 failure category
- [ ] 完成 train/dev/test 隔离检查
- [ ] 实现 LoRA-SFT training config
- [ ] 训练 SFT-100
- [ ] 训练 SFT-300
- [ ] 训练 SFT-1000
- [ ] 评估各 SFT 条件
- [ ] 比较 against Best Train-free
- [ ] 生成 scaling curve

### 12.5 风险提示
- SFT 数据质量可能决定上限
- 样本 category 分布失衡会扭曲结论
- 必须记录训练成本与 checkpoint 元数据

---

## 13. Appendix / Focused Probes 阶段

### 13.1 目标
补充支持主文结论，但不抢主线。

### 13.2 建议 probe

#### Probe A — Distractor injection
目的：
- 测 procedural support / skill support 的 precision 敏感性

#### Probe B — Summary / card corruption
目的：
- 看 procedural support 中哪些字段关键

#### Probe C — Failure-triggered loading vs static support
目的：
- 轻量测试 support timing 的影响

#### Probe D — Stale / incompatible procedure
目的：
- 看 tool/env grounding 和 procedural support 的交互

### 13.3 TODO
- [ ] 定义 focused benchmark
- [ ] 实现 distractor probe
- [ ] 实现 corruption probe
- [ ] 实现 timing probe
- [ ] 导出 appendix tables

---

## 14. 统一结果聚合与统计 TODO

### 14.1 聚合输出必须包含
- benchmark-level result tables
- condition-level summary tables
- task-level long-form CSV
- failure-category long-form CSV
- plotting-ready CSV
- paired comparison tables

### 14.2 必做分析
- [ ] bootstrap confidence intervals
- [ ] benchmark 内 paired delta
- [ ] NIR calculation
- [ ] per-category repair rate
- [ ] added cost summary
- [ ] SFT scaling summary

### 14.3 推荐分析
- [ ] mixed-effects aggregation
- [ ] logistic repair success modeling
- [ ] per-category cost-efficiency
- [ ] benchmark × category interaction analysis

---

## 15. 图表生成 TODO

### 主文图
- [ ] Figure 1: failure taxonomy distribution
- [ ] Figure 2: cost-quality frontier
- [ ] Figure 3: category-specific repair
- [ ] Figure 4: SFT scaling
- [ ] Figure 5: negative interference breakdown

### 主文表
- [ ] Table 1: benchmark suite & setup
- [ ] Table 2: main results
- [ ] Table 3: per-category repair rate

### 附录表
- [ ] detailed benchmark tables
- [ ] failure case table
- [ ] annotation agreement table
- [ ] appendix probe tables

---

## 16. Case Study TODO

### 16.1 目标
每类 taxonomy 至少准备 2–3 个代表性案例。

### 16.2 案例要求
每个 case 至少包含：
- task 背景
- Base 失败轨迹摘要
- failure category
- repair condition 的关键变化
- 为什么修好了 / 为什么没修好
- 成本变化

### 16.3 TODO
- [ ] 从 A 类中筛选 case
- [ ] 从 B 类中筛选 case
- [ ] 从 C 类中筛选 case
- [ ] 从 D 类中筛选 case
- [ ] 从 E 类中筛选 case
- [ ] 整理 case study 素材图表

---

## 17. 文档维护规则（Claude Code 必须持续更新）

Claude Code 在推进过程中必须维护以下小节：

### 17.1 Progress Snapshot
用来记录：
- 当前阶段
- 已完成事项
- 本周主要发现
- 下一步

### 17.2 Decision Log
记录关键决策，例如：
- benchmark 是否增减
- collaboration 选择了哪种 mode
- procedural support 是否进入主文
- SFT 数据规模是否调整

### 17.3 Blockers / Risks
记录：
- benchmark 接入问题
- 环境依赖问题
- 训练资源问题
- taxonomy 一致性问题
- 数据泄漏风险

### 17.4 Open Questions
记录尚未定论的问题，但不影响当前主路径推进。

---

## 18. Progress Snapshot

### 当前阶段
Stage 3 — Failure Taxonomy 阶段进行中

### 已完成
- [x] paper_plan.md drafted
- [x] experiment_schedule.md drafted
- [x] 项目目录结构重组（configs/, src/, artifacts/, docs/）
- [x] Benchmark 接入：
  - [x] SkillsBench (87 tasks)
  - [x] PinchBench (23 tasks)
  - [x] OpenClawBench (40 tasks)
  - [x] claw-bench-official (315 tasks)
  - [x] TRIBE-INC/claw-bench
  - [x] skillbench
  - [x] SciSkillBench (放弃 - 难以适配)
- [x] 统一框架 import 路径修复
- [x] run.py 添加 dotenv 加载
- [x] output_dir 路径修正为 artifacts/runs/results
- [x] **Base Baseline 运行完成** (Model: gemini-3-flash-preview)
  - [x] SkillsBench: 69.0% (46/87)
  - [x] PinchBench: 57.7% (17/23)
  - [x] OpenClawBench: 64.2% (40 tasks)
  - [x] clawbench-official: 54.8% (151/315)
  - [x] TRIBE-INC/claw-bench: 90.9% (30/33)
  - [x] skillbench: 50.0% (11/22)
- [x] HTML 可视化 Dashboard 生成
- [x] 失败任务池构建（257 tasks across 6 benchmarks）
- [x] **Failure Taxonomy 启动**
  - [x] taxonomy_rubric.md 创建完成 (A-E categories)
  - [x] pilot annotation sample 生成 (57 tasks, 2026-03-27 updated)
- [x] **师兄 EMNLP 2027 投稿参考**：main_v2_20260327.pdf + EMNLP HTML
  - [x] 论文框架已同步到 paper_plan.md
  - [x] 关键设计决策已同步（T5选择、SFT定位、Category B边界）
  - [x] Mock CRR 数据已记录（待真实数据替换）

### 进行中
- [ ] 完成 40-60 个 pilot failures 的人工阅读
- [ ] 验证/调整 taxonomy 定义

### 下一步
1. 人工阅读 pilot failures（目标 40-60 个）
2. 计算 category distribution，验证 A+E 是否占 60-68%
3. 实现 T1 (Memory) 和 T2 (Control) recipes
4. Dev selection 确定 best train-free

### 当前风险
- [x] ~~trace 保存粒度可能不足以支持详细 taxonomy 分析~~ — 已修复
  - 问题: skillbench adapter 在 `execute()` 之前捕获 `transcript_before`，但 `execute()` 内部会重置 `_transcript = []`，导致 transcript 切片错误
  - 修复: 改用 `result.transcript` 直接获取（`execute()` 返回结果中已包含正确 transcript）
  - 其他 adapters 未发现此问题
  - nanobot.py 修复: 添加 class-level logger，修复 `_logger` → `self._logger` 引用
- [ ] Category B (Tool Grounding) 可能难以修复（Mock CRR < 0.21）
  - 影响: 即使 train-free 和 SFT 都难以解决
  - 应对: 在 Limitations 中诚实披露

### 师兄 EMNLP 2027 投稿状态
- 论文框架: ✅ 基于 main_v2_20260327.pdf
- 论文结构: ✅ 8 pages main + 4 pages Appendix
- Review issues: ✅ 全部已修复
- 当前状态: ⏳ Round 2 投稿前，需填入真实实验数据
- Mock 数据: 4 benchmarks, 7 conditions, 3 SFT scales, 200 annotated failures
- 关键发现 (Mock):
  - A+E 占 60-68%（两头重、中间轻）
  - T5 (Memory+Control): +9.1pp delta, CRR_A=0.38, CRR_C=0.42
  - Category B: CRR < 0.21（最难修复）
  - SFT E类 1.73× 优势，但 NIR 高 10 倍

### Decision 006
- Topic: Benchmark transcript re-run completion
- Decision: 5/6 benchmarks successfully re-run with valid transcripts
- Result:
  - pinchbench: 62.02% (23 tasks)
  - openclawbench: 58.21% (40 tasks)
  - skillsbench: 70.1% (52/87 tasks)
  - clawbench_official: 53.0% (139/315 tasks)
  - claw-bench-tribe: FAILED - JSON parsing error in `_extract_json_summary`
    - Error: `ValueError: Failed to parse claw-bench-tribe JSON summary from output`
    - Using old successful run (90.91%, 30/33)
- Transcript validity: 491/498 non-empty
- Status: completed (2026-03-26)

### Decision 007
- Topic: transcript 保存 bug 修复
- Decision: skillbench adapter 改用 `result.transcript` 而非切片 `self.agent._transcript`
- Reason: `execute()` 内部重置 `_transcript`，导致 `transcript_before` 捕获位置无效
- Status: applied (2026-03-26)

### Decision 008
- Topic: nanobot agent _logger bug 修复
- Decision: nanobot.py 添加 class-level logger 并修复引用
- Problem: `NameError: name '_logger' is not defined` 导致 LLM 调用从未执行
- Fix: 添加 `import logging`，添加 class-level `_logger = logging.getLogger(...)`，修复所有 `_logger` → `self._logger`
- Status: applied (2026-03-26)

### Decision 009
- Topic: T5 (Memory+Control) 选为 Best Combined Train-free
- Decision: 选择 T5 而非 T3 (+Collab)
- Reason: T5 在 A、C 类都有较好覆盖，成本 (+0.03/task) 比 +Collab (+0.08/task) 更低，dev 上 +9.1pp delta 最优
- Source: 师兄 EMNLP 2027 投稿
- Status: frozen

### Decision 010
- Topic: 不评估 T5 + SFT 组合
- Decision: 不实现 T5 + SFT 组合条件
- Reason: T5 已占很低 NIR budget，额外 SFT 的 NIR 会叠加
- Source: 师兄 EMNLP 2027 投稿
- Status: frozen

### Decision 011
- Topic: Category B (Tool Grounding) 为最难修复类
- Decision: 在 Limitations 中明确讨论 Category B 可能是 model-dependent 而非 recipe-dependent
- Evidence: Mock CRR_B < 0.21
- Source: 师兄 EMNLP 2027 投稿
- Status: frozen

### Decision 012
- Topic: 师兄 EMNLP 2027 投稿参考状态
- Decision: 已同步师兄投稿的关键设计决策和 Mock 数据
- Reference: `docs/main_v2_20260327.pdf` + `docs/EMNLP 2027 Paper...`
- 当前状态: Round 2 投稿前，需填入真实实验数据
- Status: 参考完成

### Decision 013
- Topic: Benchmark 对齐说明
- Note: 师兄 EMNLP 投稿的 4 个 benchmarks 与当前项目 benchmarks 不同
- 师兄用: AgentBench-OC, PinchBench, MedSearchBench, SciResearchBench
- 我们用: AgentBench-OpenClaw, PinchBench, claw-bench-official, SkillsBench, TRIBE-INC/claw-bench, skillbench
- 当前 project 的 benchmarks 保持不变（已接入）
- Status: info only

---

## 19. Decision Log（汇总）

> 注：Decision 006-013 已移至上方 Progress Snapshot 区域。下方仅保留核心主线决策。

### Decision 001
- Topic: 论文主线
- Decision: 以”统一评测 + failure taxonomy + lightweight repair + small-data SFT 对照”为主线
- Reason: 比单独的 skill orchestration paper 更 solid
- Status: frozen

### Decision 002
- Topic: 训练设置
- Decision: 只做 small-data SFT，不做 RL
- Reason: 减少变量，突出训练边际价值
- Status: frozen

### Decision 003
- Topic: procedural support / skill orchestration 的定位
- Decision: 降级为 training-free recipe 的局部组件或 focused appendix analysis
- Reason: 避免偏离主线
- Status: frozen

---

## 20. Blockers / Risks（初始化模板）

### Risk 001
- Risk: benchmark versions 漂移
- Impact: 结果不可复现
- Mitigation: 所有 benchmark 必须 pin commit / release / task list

### Risk 002
- Risk: trace 信息不足以做 failure taxonomy
- Impact: 无法支撑核心贡献
- Mitigation: 优先补齐 step/event logging

### Risk 003
- Risk: training-free recipe 空间太大
- Impact: dev 阶段发散
- Mitigation: 保持 recipe 低自由度，只做最小可解释版本

### Risk 004
- Risk: SFT 数据构造质量不稳
- Impact: 训练结论失真
- Mitigation: 优先 corrected trajectories，记录 category 分布与样本来源

### Risk 005
- Risk: Category B (Tool Grounding) 可能难以修复
- Impact: 即使 train-free 和 SFT 都难以解决
- Mitigation: 在 Limitations 中诚实披露，可能是 model-dependent 而非 recipe-dependent
- Evidence: Mock CRR_B < 0.21

---

## 21. 最终检查清单（项目结束前必须全部满足）

### 工程
- [ ] harness 可运行
- [ ] benchmark versions 已锁定
- [ ] configs 完整
- [ ] logs 完整
- [ ] results 可追溯

### 科学性
- [ ] Base baseline 稳定
- [ ] taxonomy 已冻结
- [ ] annotation agreement 已报告
- [ ] dev/test 分离已执行
- [ ] best train-free 已冻结后再测 test
- [ ] SFT 数据规模与来源清晰

### 结果
- [ ] 主文表完成
- [ ] 主文图完成
- [ ] 附录表完成
- [ ] case studies 完成
- [ ] paired delta / NIR / CRR / cost 全部齐备

### 写作
- [ ] methods notes 完成
- [ ] appendix notes 完成
- [ ] key observations memo 完成
- [ ] 所有图表可直接进入论文草稿

---

## 22. 一句话版本（供 Claude Code 始终记住）

这份 schedule 的作用不是“列任务”，而是：

> 让整个项目严格按“先复现与基线、再 taxonomy、再 training-free、再 SFT、最后补充 probe”的路径推进，并在每一步都留下可复查、可聚合、可写论文的结果。

---
