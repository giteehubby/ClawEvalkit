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

## 3. 目录与工程组织 TODO

### 3.1 目标目录结构（建议）
项目需要至少具备如下逻辑目录：

- `configs/`
  - `benchmarks/`
  - `conditions/`
  - `experiments/`
- `src/`
  - `harness/`
  - `runners/`
  - `conditions/`
  - `logging/`
  - `analysis/`
  - `annotation/`
  - `training/`
- `artifacts/`
  - `runs/`
  - `aggregates/`
  - `plots/`
  - `tables/`
  - `failure_cases/`
- `docs/`
  - `paper_plan.md`
  - `experiment_schedule.md`
  - `taxonomy_rubric.md`
  - `methods_notes.md`
- `scripts/`
  - run scripts
  - aggregate scripts
  - plotting scripts
  - export scripts

### 3.2 TODO
- [ ] 创建统一项目目录结构
- [ ] 创建 README / quickstart
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
- Base baseline per benchmark
- 成本统计
- 失败任务池
- 原始 trace 与 artifacts
- 初始 failure evidence 导出

### 7.3 TODO
- [ ] 跑通单 benchmark smoke test
- [ ] 跑通 Base OpenClaw on AgentBench-OpenClaw
- [ ] 跑通 Base OpenClaw on official Claw Bench quick subset
- [ ] 跑通 Base OpenClaw on PinchBench
- [ ] 跑通 Base OpenClaw on SkillsBench
- [ ] 跑通 Base OpenClaw on TRIBE-INC/claw-bench
- [ ] ~~跑通 Base OpenClaw on SciSkillBench~~ — 已放弃
- [ ] 导出统一 baseline summary table
- [ ] 导出失败 run 列表与 evidence links

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
- [ ] 建立 failure sample export script
- [ ] 创建 taxonomy_rubric.md
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
- [ ] 选定 collaboration mode
- [ ] 定义角色职责
- [ ] 实现 handoff protocol
- [ ] 实现 collaboration event logging
- [ ] 在 dev 上跑 smoke ablation
- [ ] 比较 collaboration 的额外成本

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

## 18. Progress Snapshot（初始化模板）

### 当前阶段
Stage 0 — Harness setup

### 已完成
- [ ] paper_plan.md drafted
- [ ] experiment_schedule.md drafted

### 进行中
- [ ] project structure setup
- [ ] config schema draft
- [ ] benchmark runner inspection

### 下一步
1. 创建统一目录和 schema
2. 接入第一个 benchmark runner
3. 跑 Base smoke test
4. 打通 logging pipeline

### 当前风险
- benchmark 接入复杂度未知
- scoring implementation 可能不统一
- trace 保存粒度可能不足以支持 taxonomy

---

## 19. Decision Log（初始化模板）

### Decision 001
- Topic: 论文主线
- Decision: 以“统一评测 + failure taxonomy + lightweight repair + small-data SFT 对照”为主线
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