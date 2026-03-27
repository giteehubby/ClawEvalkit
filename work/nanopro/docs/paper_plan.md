# OpenClaw Paper Plan
## Unified Evaluation, Failure Taxonomy, and Lightweight Repair Recipes for OpenClaw-like Agents

---

## 0. 本文档目的

本文档用于告诉 Claude Code：这篇论文到底要解决什么问题、主线是什么、哪些东西是主贡献、哪些东西只是辅助分析，以及整个项目的研究边界和交付目标。

Claude Code 在后续所有工程、实验、统计、画图、日志、分析、备忘录撰写中，都应以本文件为最高层研究蓝图。

这篇论文的目标不是提出一个复杂的新 agent framework，也不是再做一篇泛泛的 benchmark paper，而是围绕以下主线展开：

> 我们希望系统研究：OpenClaw-like 开源 agents 的失败是否集中在少数几个稳定的系统性缺陷上；这些缺陷能否被低成本、可复现的 lightweight recipes 修复；以及 small-data SFT 相比 training-free recipes 到底多修了什么、值不值得。

---

## 1. 论文核心 framing

### 1.1 我们不再主打什么

本项目**不再**把以下命题作为整篇论文的唯一主问题：

- “skills 是否有用”
- “skill orchestration 怎样设计最优”
- “某个 fancy multi-agent 架构能否提升分数”
- “我们集成了很多 benchmark”

这些内容可以存在，但只能作为子结论、局部机制分析、或工程支撑，不应主导整篇论文。

### 1.2 我们要主打什么

这篇论文真正想回答的是三个层次的问题：

#### Level 1 — 诊断
OpenClaw-like 开源 agents 的主要问题究竟是什么？  
这些失败是否集中在少数几个跨 benchmark 稳定出现的系统性缺陷上？

#### Level 2 — 修复
这些缺陷里，哪些可以通过**training-free recipes** 修复？  
例如：任务局部记忆、单 agent 控制策略、轻量 verifier / collaboration、结构化 procedural support 等。

#### Level 3 — 训练的边际价值
在 training-free recipes 的基础上，small-data SFT 还能修多少？  
它修复的是哪类问题？  
它与 training-free 是替代关系，还是互补关系？

### 1.3 核心主张

本论文的核心主张应当是：

> OpenClaw-like agents 的不足并不是完全随机的，也不只是“模型不够强”这么简单；其失败可以被归纳为少数几个可操作、可统计、可修复的核心类别。许多提升可以通过轻量、training-free 的系统级 recipe 获得，而 small-data SFT 主要在部分更困难、更程序性、更长尾的失败类别上提供额外收益。

---

## 2. 推荐论文标题与摘要方向

### 2.1 推荐标题

#### 标题版本 A（最稳）
**Diagnosing and Strengthening OpenClaw-like Agents: Unified Evaluation, Failure Taxonomy, and Lightweight Repair Recipes**

#### 标题版本 B（更强调闭环）
**From Evaluation to Repair: A Unified Study of Failure Modes and Lightweight Fixes for OpenClaw-like Agents**

#### 标题版本 C（更偏系统研究）
**A Unified Study of Evaluation, Failure Taxonomy, and Lightweight Repair for OpenClaw-like Agents**

中文可对应为：

- 《OpenClaw-like Agents 的统一评测、缺陷诊断与轻量修复研究》
- 《从评测到修复：OpenClaw-like Agents 的失败模式与轻量修复统一研究》

### 2.2 摘要核心表达方向

摘要建议围绕如下四句话组织：

1. 现有开源 generalist agents 缺乏统一、细粒度、可修复导向的分析框架；
2. 我们提出一个统一 evaluation harness，并归纳出 5 类核心 failure taxonomy；
3. 我们系统比较 training-free repair recipes 与 small-data SFT 的作用边界；
4. 我们发现大量收益可由轻量 recipe 获得，而 SFT 的额外价值主要集中在更难、更程序性、更长尾的类别上。

---

## 3. 三个主贡献（必须在正文与答辩中始终一致）

### Contribution 1 — Unified evaluation harness

我们构建一个统一的 evaluation harness / suite，用来：

- pin benchmark versions
- pin task subsets / splits
- 统一 runner interface
- 统一 logging schema
- 统一 trace / artifact 保存
- 统一 token / tool / latency / step 成本记录
- 统一 within-benchmark paired comparison protocol
- 统一 failure evidence 导出

这部分贡献不是“集成很多 benchmark”，而是：

> 提供一个用于 agent 诊断与修复研究的统一协议层。

### Contribution 2 — Failure taxonomy A–E

我们通过跨 benchmark 的失败轨迹分析，定义并验证 5 类核心 failure types：

- A. Task understanding / planning drift
- B. Tool / environment grounding failure
- C. Memory / state management failure
- D. Verification / recovery deficiency
- E. Long-tail procedural knowledge / skill execution deficiency

要求：

- 每一类必须有可操作定义
- 必须有标注规范
- 必须有 evidence criteria
- 必须有 prevalence 统计
- 必须在一个人工核验子集上报告标注一致性

### Contribution 3 — Lightweight repair study

我们围绕这些 failure types，系统比较两类 repair pathways：

#### Training-free recipes
- task-local episodic memory
- single-agent control recipe
- minimal collaboration / verifier
- optional structured procedural support

#### Small-data SFT
- LoRA-SFT / adapter-SFT
- 小规模训练数据（如 100 / 300 / 1000）
- 平衡 failure category 的训练集构造
- 测试其与 training-free repair 的关系

---

## 4. 明确研究边界（必须严格遵守）

### 4.1 本项目优先研究什么

优先研究：

- OpenClaw-like agents 的系统级缺陷
- inference-time repair
- reproducible evaluation
- per-category repair analysis
- training-free vs small-data SFT 的对照

### 4.2 本项目暂不优先研究什么

本项目**不优先**研究：

- RL 或强化学习微调
- 非常复杂的多 agent 社会结构
- 大规模自动生成训练数据的全链条
- 一个全新的复杂 selector / planner / memory architecture
- 大而全的 benchmark collection paper
- “skill orchestration” 的完整方法论文

### 4.3 关于 skill orchestration 的位置

本项目承认 skill orchestration 是有价值的，但它在本论文中的位置应被严格限定为：

- 一种可能的 training-free procedural support recipe
- 或一种针对 E 类 failure 的 focused mechanism analysis
- 或 appendix 中的补充实验

它**不是**整篇论文的唯一主轴。

---

## 5. 研究问题（Research Questions）

### RQ1
OpenClaw-like agents 的失败，是否会集中在少数几个可重复出现的系统性类别中？

### RQ2
不同 benchmark / task domain 中，这些 failure categories 的分布是否稳定、是否存在显著差异？

### RQ3
哪些 failure categories 可以被 training-free recipes 有效修复？

### RQ4
small-data SFT 相比 best training-free recipe，会额外修复哪些类别？其收益是否具有数据效率？

### RQ5
训练-free recipes 与 SFT 的收益-成本关系是什么？  
包括：
- score gain
- negative interference
- token cost
- tool cost
- step cost
- latency

### RQ6
针对 long-tail procedural / skill-like tasks，结构化 procedural support 是否能提供额外增益？

---

## 6. 核心假设（Hypotheses）

### H1
OpenClaw-like agents 的失败不是均匀噪声，而是集中于 5 类主要 failure modes。

### H2
A/B/C/D 类 failures 中，有相当一部分可通过 training-free recipes 显著缓解。

### H3
E 类 failures（长尾程序性知识 / skill execution）更依赖 structured procedural support 或 small-data SFT。

### H4
许多收益来自系统层控制、记忆和恢复机制，而不是额外训练本身。

### H5
small-data SFT 的额外增益主要出现在更难、更程序性、更长尾的 failure categories 上。

### H6
某些 repair 方法虽然提高均值，但会增加 negative interference，因此必须单独报告代价与副作用。

---

## 7. Failure Taxonomy A–E（冻结版草案）

> 注意：这里是研究蓝图层面的 taxonomy 定义。
> Claude Code 可以在 pilot 阶段提出微调建议，但一旦进入正式标注与主实验，taxonomy 和 rubric 必须冻结。

### 7.1 关键预期发现（来自师兄 EMNLP 2027 投稿的 Mock 数据）

> ⚠️ 以下数据为 Mock 结果，用于指引研究方向。真实数据替换后应以实验结果为准。

#### A+E 占 60-68%：两头重、中间轻

大部分失败集中在：
- **A 类（Task Understanding）**：高层计划问题
- **E 类（Procedural Skill）**：低层程序性知识问题
- B/C/D 类（Tool Grounding / Memory / Verification）反而较少

这意味着本论文的核心战场在 **A（计划）** 和 **E（程序性知识）** 两端。

#### Category B 是"最难修复"的类

无论 train-free 还是 SFT，Category B 的 CRR 都 < 0.21。这可能是 **model-dependent** 而非 **recipe-dependent** 的问题。在 Limitations 中需明确讨论此边界。

#### CRR 分布（Mock 数据）

| Category | Best Recipe | CRR (Mock) |
|----------|-------------|------------|
| A. Task Understanding | +Control | 0.38 |
| B. Tool Grounding | SFT-1000 | 0.21 |
| C. Memory/State | +Memory | 0.42 |
| D. Verification | +Collab | 0.45 |
| E. Procedural Skill | SFT-1000 | 0.19 |

#### 稳定性证据
- **跨 benchmark 稳定性**：Pearson r = 0.94
- **标注一致性**：Cohen's κ = 0.78 (substantial agreement)
- **标注规模**：60 pilot + 140 formal = 200 cases

### 7.2 T5（Memory+Control）作为 Best Combined Train-free 的设计决策

选择 T5（Memory+Control）而非 T3（+Collab）的原因：
- +Collab 的 NIR 最低 (0.5%)，但 CRR_D 虽高 (0.45) 只覆盖 D 类
- T5 在 A、C 类都有较好覆盖，成本 (+0.03/task) 比 +Collab (+0.08/task) 更低
- Dev 上 T5 的 +9.1pp delta 最优

### 7.3 SFT 与 Train-free 的互补关系（非替代）

- Train-free recipes 可修复 A-D 类 28-45% 失败（成本接近零）
- SFT 在 E 类（程序性知识）上有 1.73× 优势，但 NIR 高出 10 倍
- **实践路径**：先 T5 确认边界，再决定是否上 SFT
- **不评估 T5 + SFT 组合**：因为 T5 已占很低 NIR budget，额外 SFT 的 NIR 会叠加

### A. Task Understanding / Planning Drift
定义：模型未正确理解任务要求、约束、目标，或在多步过程中逐渐偏离核心目标。

典型迹象：
- 初始 plan 就漏约束
- 计划与任务不匹配
- 中后期步骤偏题
- 忘记终极 deliverable 的要求

候选修复：
- plan-first
- explicit subgoal tracking
- periodic replanning
- planner-executor split

### B. Tool / Environment Grounding Failure
定义：模型无法正确把任务意图映射到工具调用、环境操作、参数、路径、格式、依赖等实际执行层。

典型迹象：
- 选错工具
- 参数/命令错误
- 路径或权限错误
- 依赖/环境前提不满足
- 输出格式与工具要求不兼容

候选修复：
- environment readiness check
- tool schema grounding
- retry / fallback rules
- execution preflight checks

### C. Memory / State Management Failure
定义：模型不能稳定维护任务中间状态、上下文事实、已完成步骤、已生成 artifacts、失败历史等。

典型迹象：
- 重复劳动
- 忘记先前搜索结果
- 文件状态混乱
- 中间变量/路径/版本信息丢失
- 上下文过长导致关键状态被覆盖

候选修复：
- task-local episodic memory
- structured state tracker
- retrieval from local memory
- artifact registry

### D. Verification / Recovery Deficiency
定义：模型缺乏自我检查、错误检测、失败恢复、rollback 或 debug 能力。

典型迹象：
- 工具报错后忽略
- 进入无效循环
- 出错后不会定位问题
- 修复策略单一且失败
- 缺乏 sanity check

候选修复：
- verifier / critic
- failure-triggered reflection
- explicit recovery policy
- retry with diagnosis
- executor-verifier collaboration

### E. Long-tail Procedural Knowledge / Skill Execution Deficiency
定义：模型理解任务大方向，但缺乏某类程序性知识、结构化步骤 knowledge、操作 recipe 或领域 procedural know-how。

典型迹象：
- 知道要做什么，但不会正确做
- 专业任务执行次序错误
- 漏 prerequisite
- procedural detail 错误
- 需要结构化 skill 才能完成

候选修复：
- structured procedural support
- skill cards / on-demand expansion
- exemplar-based support
- small-data SFT

---

## 8. Failure 标注原则

### 8.1 标注目标

标注的目的不是“解释一切”，而是建立一个：

- 能用于统计分析
- 能用于 per-category repair 分析
- 能用于 case study
- 能复核一致性

的 failure analysis protocol。

### 8.2 标注单位

建议以 **task run** 为基本单位。

如果一个 task 在某个 condition 下失败，则为该失败 run 标注：

- dominant category（A–E 之一）
- optional secondary note（自由文本）
- evidence snippet
- confidence（high / medium / low）

### 8.3 标注流程

建议流程：

1. Pilot：人工阅读 40–60 个失败样本，形成初版 rubric；
2. 冻结 taxonomy 与 rubric；
3. 正式阶段：随机抽取 150–200 个失败 run 做双人标注；
4. 计算 agreement（如 Cohen’s kappa）；
5. 其余失败 run 可用 heuristics / model assistance 做弱标注，但主结论优先依赖人工核验子集。

### 8.4 标注原则

- 必须选 dominant category
- 不要因为一个失败样本复杂，就回避主因判断
- 若证据不足，允许标 confidence low
- taxonomy 不追求哲学完美，而追求研究可操作性

---

## 9. Benchmarks 与使用策略

### 9.1 benchmark 选择原则

我们选择 benchmark 的原则不是”越多越好”，而是：

- task style 多样
- failure mode 可观察
- runner 可稳定复现
- 适合 paired comparison
- 能提供真实 agent traces
- 覆盖一般任务与长尾程序性任务

### 9.2 主 benchmark 完成状态

| Benchmark | Status | 用途 |
|-----------|--------|------|
| AgentBench-OpenClaw | ✅ 已完成 | general multi-step tasks, planning, tool use, recovery |
| PinchBench | ✅ 已完成 | messy real-world productivity / analysis tasks, tool grounding, memory, verification |
| claw-bench (official) | ✅ 已完成 | breadth coverage, sanity check |
| SkillsBench | ✅ 已完成 | procedural support / skill-focused probing |
| TRIBE-INC/claw-bench | ✅ 已完成 | failure diagnosis / focused probes |
| skillbench | ✅ 已完成 | |
| SciSkillBench | ❌ 已放弃 | 难以适配 |

### 9.3 主 benchmark 描述

#### B1 — AgentBench-OpenClaw
用途：
- general multi-step tasks
- 观察 planning、tool use、recovery

#### B2 — PinchBench
用途：
- messy real-world productivity / analysis tasks
- 观察 tool grounding、memory、verification

#### B3 — official Claw Bench（lightweight breadth sanity）
用途：
- breadth coverage
- sanity check

#### B4 — SkillsBench
用途：
- procedural support / skill-focused probing

#### B5 — TRIBE-INC/claw-bench
用途：
- failure diagnosis / focused probes

### 9.4 benchmark 使用规范

每个 benchmark 必须：

- pin 版本 / commit / release
- pin task subset / split
- 明确 scoring implementation
- 单独报告结果
- 先做 within-benchmark paired comparison，再做 cross-benchmark 汇总

不得：
- 直接将 raw scores 跨 benchmark 简单平均
- 混淆 benchmark 版本
- 在主结果中隐去任务数和条件

---

## 10. 比较条件（Conditions）

### 10.1 Base condition
**Base OpenClaw**

作用：
- 所有 paired comparison 的 anchor
- 所有 repair 分析的起点

### 10.2 Training-free repair conditions

#### T1 — Memory
任务局部 episodic memory：
- 记录中间事实
- 记录 artifact / 文件路径
- 记录失败历史
- 记录已验证结论

#### T2 — Single-agent control recipe
例如：
- plan-first
- periodic replanning
- explicit subgoal tracking
- bounded retries
- failure-triggered reflection
- tool preflight / retry strategy

#### T3 — Minimal collaboration
建议只保留最小、可解释的二角色方案之一：
- planner-executor
- executor-verifier

不要做复杂的多 agent 社会结构。

#### T4 — Optional procedural support
该条件不是主角，但可以作为：
- T2 的一个子组件
- 或单独作为 E 类 focused repair

内容可包括：
- structured skill cards
- on-demand raw expansion
- compact procedural examples

### 10.3 Combined training-free condition

#### T5 — Best Combined Train-free
在 dev split 上选出 best combined train-free recipe，冻结后在 test split 上正式评估。

### 10.4 Training condition

#### S1 / S2 / S3 — Small-data SFT
建议数据规模：
- 100
- 300
- 1000

如预算有限，可退化为：
- 50
- 200
- 500

要求：
- 优先 LoRA-SFT / adapter-SFT
- 尽量平衡 failure categories
- 数据来源与构造过程必须可追踪
- 严格区分 train / dev / test

### 10.5 可选组合条件

若预算允许，可增加：
- Best Train-free + SFT

用于分析二者是否互补。

---

## 11. Procedural support / skill orchestration 的定位

### 11.1 保留但降级

本项目保留 procedural support / skill orchestration 的价值，但应明确其角色：

- 它是 E 类 failure 的一种 repair candidate
- 它可作为 T2 的局部模块
- 它可在 appendix 中做 focused analysis

### 11.2 不再展开的大矩阵

以下旧思路不作为主文主矩阵：

- K 轴大规模 sweep
- timing 轴全套 sweep
- representation 轴全套 sweep
- precision / recall selector 大规模机制图谱

如需保留，只能在：
- appendix
- focused benchmark
- E 类专题分析

中局部进行。

---

## 12. 核心指标（Metrics）

### M1 — Within-benchmark paired delta
相对 Base OpenClaw：

Δ_b(c) = Avg_t [ score(c, t, b) - score(Base, t, b) ]

要求：
- 每个 benchmark 单独汇报
- 提供 mean ± 95% bootstrap CI

### M2 — Negative-interference rate (NIR)
NIR(c) = % { t : score(c,t,b) < score(Base,t,b) }

解释：
- repair 不仅要看平均提升，也要看会不会“害人”

### M3 — Added cost
至少记录：
- extra prompt tokens
- tool calls
- steps
- wall-clock runtime / latency（可放附录）

### M4 — Category Repair Rate (CRR)
对于 category k：

CRR_k(c) = P(task repaired under c | Base failed with category k)

这是本论文最重要的分析指标之一。

### M5 — SFT data efficiency
比较：
- SFT-100 / 300 / 1000
- 以及它们相对 best train-free 的增益与成本

### M6 — Annotation reliability
- inter-annotator agreement
- kappa / percent agreement

---

## 13. 统计分析原则

### 13.1 必做
- task-level bootstrap confidence intervals
- within-benchmark paired analysis
- mixed-effects style cross-benchmark aggregation（如可实现）

### 13.2 推荐模型
例如：

score ~ condition + benchmark + category + interactions + (1 | task)

或：

repair_success ~ condition + category + benchmark + (1 | task)

### 13.3 统计报告要求
所有主结果至少给出：
- mean
- confidence interval
- task count n
- benchmark version
- condition 全称

---

## 14. 主文结构建议

### Main Paper (8 pages)

| Section | Content |
|---------|---------|
| Abstract | 4句话：统一评测→失败分类→train-free修复→SFT边际价值 |
| 1. Introduction | 问题陈述 + Fig1(分类分布) + 4个贡献点 |
| 2. Unified Evaluation Harness | 4 benchmarks, 7 conditions, cost accounting, paired delta/NIR/CRR指标 |
| 3. Failure Taxonomy (A-E) | 分类定义, 标注协议(κ=0.78), 分布稳定性(r=0.94) |
| 4. Training-free Recipes (T1-T5) | T1(Memory), T2(Control), T3(Collab), T4(ProcSupport), T5(Combined) |
| 5. Small-data SFT Study | 数据构造, category平衡, research questions, 互补性假设 |
| 6. Experiments | Dev selection + Main results + CRR + Cost-benefit + Cases |
| 7. Related Work | Agent eval, train-free improvement, failure analysis, small-data SFT |
| 8. Conclusion | 三层贡献 + Limitations |

### Appendix (4 pages)

| Appendix | Content |
|----------|---------|
| A. Per-Benchmark | 4个benchmark各自的delta/NIR详细数字 |
| B. T5 Ablation | Memory alone / Control alone / Memory+Control 的CRR对比 |
| C. SFT Data | GPT-4o trajectory correction prompt template + 人工verification结果 |
| D. Annotation | 标注协议详情: pilot(60) → formal(140), Cohen's κ=0.78 |
| E. Baselines | Human ceiling, inter-condition correlation matrix |

---

## 15. 主表与主图建议

### Table 1 — Benchmark suite and setup
列：benchmark, task type, tool intensity, long-horizon, procedural intensity, version/commit, task count

### Table 2 — Main results
> ⚠️ Table 2 需新增 "Base Acc." 列，用于报告 Base 的绝对准确率。

条件：
- Base（需新增 Base Acc. 列）
- Best single training-free recipe
- Best combined train-free
- SFT-100
- SFT-300
- SFT-1000

列：
- Base Acc.
- Paired Delta
- 95% CI
- NIR
- extra tokens
- tool calls
- steps

### Table 3 — Per-category repair rate
行：A–E
列：各主要 condition 的 CRR

### Figure 1 — Failure taxonomy distribution
展示各 benchmark 上 A–E 的占比，强调 A+E 占 60-68%

### Figure 2 — Cost-quality frontier
x 轴：added cost
y 轴：paired delta

### Figure 3 — Category-specific repair heatmap / bar chart
比较不同 repair 对 A–E 的作用

### Figure 4 — SFT scaling curve
样本量 vs paired delta / per-category repair

### Figure 5 — Negative interference breakdown
看哪些条件在什么任务上伤害最大

---

## 16. 项目执行优先级（Claude Code 必须遵守）

1. reproducibility first  
2. benchmark pinning first  
3. logging / trace integrity first  
4. Base + taxonomy first  
5. training-free first  
6. dev/test separation first  
7. SFT after train-free baselines are stable  
8. appendix probes last

---

## 17. Claude Code 的行为约束

Claude Code 在整个项目中必须遵守：

### 17.1 不允许
- 先随便调 recipe 再回头补 baseline
- 在 test split 上挑选最佳 recipe
- benchmark 版本不固定
- 无日志地跑实验
- 结果与 config 无法一一对应
- 把 procedural support / orchestration 升级成新的主轴，偏离本论文 framing

### 17.2 必须做到
- 每个 run 可追溯到 config + code commit + benchmark version + seed
- 所有输出可聚合成统一表格
- failure evidence 可导出
- 中间分析 memo 持续更新
- 主文与附录实验有明确层级

---

## 18. 最终交付物

本项目最终至少需要交付：

1. 统一 evaluation harness 代码框架  
2. benchmark runners 与 pinned setup  
3. 统一 config schema  
4. 统一 logging schema  
5. Base OpenClaw 基线结果  
6. failure taxonomy rubric  
7. failure annotation 子集与 agreement 统计  
8. training-free recipes 实现  
9. best train-free condition 的正式结果  
10. small-data SFT 实验结果  
11. 主结果表、附录表、plot-ready CSV  
12. case study 素材  
13. paper-ready figures  
14. methods / appendix 草稿  
15. 持续更新的 experiment_schedule.md

---

## 19. 一句话版本（供 Claude Code 始终记住）

这篇论文的核心不是“某个技巧让分数更高”，而是：

> 用统一协议诊断 OpenClaw-like agents 的系统性失败，证明许多问题可被低成本 training-free recipes 修复，并明确 small-data SFT 的额外价值和边界。

---