# PinchBench & AgentBench-OC — Failure Analysis Summary
Generated: 2026-03-27 | Data: work/exp89_claw_benchmarks/assets/output/

---

## 一、PinchBench 评估结果概览

### 1.1 整体分数分布（17次运行）

| Endpoint | 运行次数 | Mean | Min | Max | Std |
|---|---|---|---|---|---|
| Seed18_new (kq8ft) | 2 | 0.911 | 0.822 | 1.000 | 0.126 |
| Seed18_old (sxgvt) | 6 | 0.677 | 0.544 | 0.814 | 0.106 |
| jx2qv | 9 | 0.604 | 0.058 | 0.847 | 0.251 |

**关键发现：同一 endpoint（jx2qv）上，整体分数从 0.058 到 0.847，跨度极大（std=0.251）。** API 变异性是主要噪声来源，导致 5pp 以内的差异不可解读。

### 1.2 任务级失败分布（23个任务，17次运行）

| 任务ID | Mean | Min | Max | Std | #<0.5 | 失败类型 |
|---|---|---|---|---|---|---|
| task_13_image_gen | 0.088 | 0.000 | 0.500 | 0.128 | **15/16** | **E型（工具缺失）** |
| task_15_daily_summary | 0.290 | 0.000 | 0.950 | 0.380 | **12/16** | **A型（初始化污染）** |
| task_06_events | 0.284 | 0.000 | 0.940 | 0.390 | **11/16** | **D型（验证缺失）** |
| task_14_humanizer | 0.426 | 0.000 | 0.960 | 0.385 | 7/16 | B/D混合 |
| task_20_eli5_pdf_summary | 0.505 | 0.000 | 1.000 | 0.409 | 6/16 | E型（PDF工具缺失） |
| task_05_summary | 0.564 | 0.000 | 0.940 | 0.401 | 5/16 | A型（规划漂移） |
| task_08_memory | 0.569 | 0.000 | 0.700 | 0.282 | 3/16 | C型（状态管理） |
| task_10_workflow | 0.656 | 0.000 | 0.917 | 0.272 | 6/16 | B型（配置未读） |

---

## 二、结构性失败案例详解

### 2.1 E型失败（工具/基础设施缺失）— 最难修复

#### task_13_image_gen（AI图像生成）

- **失败频率**: 15/16 次运行 score < 0.5，最高仅 0.50
- **根本原因**: nanobot 运行时**没有图像生成工具**（`image` 工具只能分析，不能生成）。Agent 反复尝试访问不存在的工具（`generate_image`, HuggingFace API），超时后放弃
- **Judge 评价摘录**:
  > "The agent completely failed to generate the requested image. They made multiple unsuccessful attempts to access image generation tools/APIs and created irrelevant files instead."
  > "Agent attempted a reasonable prompt with all key elements but no generate_image tool exists in the available toolset."
- **修复结论**: 这是**基础设施级别**的问题，加 memory 或 plan-first prompt 无济于事，必须在运行时添加图像生成工具
- **分类置信度**: 高（明显是工具缺失，没有争议）

#### task_20_eli5_pdf_summary（PDF阅读）

- **失败频率**: 6/16 次 score < 0.5，但有 4 次达到 1.0（PDF 偶尔能读）
- **根本原因**: nanobot 运行时**没有 PDF 阅读工具**。Agent 用 `web_search` / `file_listing` 尝试读取 PDF 均失败。偶有成功是因为某次运行中碰巧用了某种替代方法
- **Judge 评价摘录**:
  > "The agent failed to execute any of the required task steps. It did not read the GPT4.pdf file, did not generate the ELI5 summary, and did not save anything to eli5_summary.txt."
- **修复结论**: 同 task_13，需要添加 PDF 阅读工具
- **分类置信度**: 高

---

### 2.2 A型失败（任务理解/规划漂移）

#### task_15_daily_summary（每日研究摘要）

- **失败频率**: 12/16 次 score < 0.5，其中 7 次得 0.0
- **根本原因**: nanobot 初始化时在 workspace 创建 **AGENTS.md 和 HEARTBEAT.md 文件**。Agent 将这些文件误读为任务上下文或指令，花费大量 tool call 维护这些文件，而不是读取 `research/` 目录下的真实数据
- **Judge 评价摘录**:
  > "Instead of reviewing files in the research/ directory and creating the requested daily briefing, it created unrelated files (AGENTS.md, HEARTBEAT.md, etc.) and performed none of the steps necessary."
  > "The agent completely failed to meet task requirements. Instead of exploring the research directory, it created unrelated files."
- **修复结论**: 这是一个**基础设施-Agent 交互**导致的 A 型失败——不是 Agent 能力问题，而是初始化产物与任务执行的冲突。隔离初始化过程可解决
- **分类置信度**: 高（多次运行均为 AGENTS.md 污染）

#### task_05_summary（文本摘要）

- **失败频率**: 5/16 次 score < 0.5，且得分两极化（0.0 或 0.82-0.94）
- **根本原因**: Agent 有时（低分时）完全忽略 `summary_source.txt`，转而发送无意义的 hello 消息；有高分运行则正确读取源文件并生成摘要
- **Judge 评价摘录**:
  > "The agent never attempted to read summary_source.txt or write any summary. Instead, it repeatedly tried to send 'Hello, I'm ready!' messages."
- **修复结论**: 偶发性规划漂移，可能与 context 状态或 API 随机性有关
- **分类置信度**: 中（A 型特征明显，但偶发不是结构性）

---

### 2.3 B型失败（工具使用/环境接地）

#### task_10_workflow（多步骤API工作流）

- **失败频率**: 6/16 次 score < 0.5，最高 0.917（exp87_ratio5pct_step660 运行中仅 0.42）
- **根本原因**: Agent **没有先读 config.json 获取 API credentials/endpoint URL**，直接生成了语法正确但无法执行的 Python 脚本。LLM Judge 因此给 0 分（脚本质量、文档、流程理解均为 0）
- **Judge 评分拆解**:
  - 自动化检查: read_config=0.0, script_created=1.0, valid_syntax=1.0, parses_json=1.0, has_http_request=1.0, notes_created=1.0
  - LLM Judge: script_quality=0.0, documentation_quality=0.0, process_understanding=0.0
- **修复结论**: 这是典型的 B 型失败——Agent 知道要生成 Python 脚本，但不知道在使用工具前需要先读配置文件。Plan-first prompting 或 preflight check recipe 可修复
- **分类置信度**: 高

---

### 2.4 D型失败（验证/恢复能力缺失）

#### task_06_events（技术会议列表）

- **失败频率**: 11/16 次 score < 0.5，mean=0.284，两极化（0.0 或 0.85-0.94）
- **根本原因**: 低分运行时 Agent **完全失败**：既不搜索技术会议也不创建 `events.md`。有些运行得 0 分是因为创建了无关文件而非目标文件，说明 Agent 没有**验证输出**是否符合任务要求
- **Judge 评价摘录**:
  > "Agent completely failed. No web searches performed, no conferences identified, no events.md file created."
  > "The agent failed to perform any work related to finding tech conferences. Instead, it created unrelated markdown files."
- **修复结论**: D 型失败，缺少 self-checking 机制导致 Agent 不知道自己的输出不完整就结束了
- **分类置信度**: 中（与 A 型有一定重叠，部分失败表现为规划漂移）

---

## 三、AgentBench-OC 失败分析

### 3.1 Memory Domain — 结构性C型失败

**所有 13 个模型变体**在 memory domain 上得分**完全相同：50.0/100**。

| 模型 | Memory Score | 备注 |
|---|---|---|
| exp87_step170 | 50.0 | 早期 checkpoint |
| exp87_ratio5pct_step1320 | 50.0 | 5% FC-high ratio |
| exp87_step1360 | 50.0 | |
| exp87_step680 | 50.0 | |
| exp91_skill_correct_step68 | 50.0 | |
| long_rl | 50.0 | |
| seed18 | 50.0 | 原始 seed18 |

**5个 memory 任务**: constraint-accumulation, context-retention, interleaved-projects, memory-organization, recall-distraction

- **根本原因**: nanobot 的 AGENTS.md/SOUL.md 初始化机制**不支持 memory domain 所需的跨会话记忆和约束跟踪**。这 50.0 分可能来自随机正确率或极少的答对题目
- **结论**: 纯 C 型失败，且是**基础设施级别**的，任何 training-free recipe 或 SFT 都需要配合基础设施改进才能真正解决

### 3.2 其他 Domain 观察

| Domain | 观察 | 备注 |
|---|---|---|
| research | 91-100 | Near-ceiling，baseline 就很强 |
| file-creation | 91-96 | Near-ceiling |
| tool-efficiency | 60-80 | 相对稳定 |
| data-analysis | 73-91 | 最多变体（exp87_ratio5pct_step1320 达到 90.0，vs others ~73-79） |
| error-handling | 45-75 | 较大方差 |
| multi-step | 60-100 | 高度依赖模型版本 |

---

## 四、失败分类汇总

### 4.1 按类型统计

| 类型 | 任务 | 频率 | 根本原因 | 修复路径 |
|---|---|---|---|---|
| **E**（工具缺失） | task_13_image_gen, task_20_eli5_pdf | 结构性，13-17% PinchBench 任务 | nanobot 缺少图像生成和 PDF 阅读工具 | **基础设施修复**（添加工具），prompting 无效 |
| **A**（规划漂移） | task_15_daily_summary | 结构性（75% 运行 <0.5） | AGENTS.md 污染 workspace，初始化与任务冲突 | 隔离初始化；修改 nanobot 启动逻辑 |
| **B**（工具接地） | task_10_workflow | 条件性（特定模型/运行时） | 不知道先读 config.json 再生成脚本 | Plan-first prompting；preflight check |
| **C**（状态管理） | AgentBench memory domain | 结构性（100% 模型均为 50.0） | nanobot 基础设施不支撑跨会话记忆 | 需要基础设施级改进；SFT 可能有效 |
| **D**（验证缺失） | task_06_events | 条件性（高方差） | Agent 不验证输出是否满足任务目标 | 添加 verifier/critic recipe |
| **B/D混合** | task_14_humanizer | 高方差（std=0.385） | 工具类型混淆（slash command vs bash command） | 澄清工具类型；retry with diagnosis |

### 4.2 跨 benchmark 的发现

1. **E 型失败是最容易诊断的**：image_gen 和 PDF 任务一看便知是工具缺失，不需要标注
2. **A 型失败（task_15）是基础设施-行为交互**：不是纯 prompt 问题，需要修改初始化流程
3. **Memory domain 在 AgentBench 上是纯 C 型**：13 个模型完全一致，强烈暗示这是系统设计问题而非模型能力问题
4. **API 方差是主要噪声**：同一 endpoint 上 0.058-0.847 的跨度说明在报告分数差异时需要大样本或 bootstrap，不宜对 <5pp 差异做结论

---

## 五、结论

- **E 型失败（13-17% 任务）**：需要基础设施修复，prompting 和 SFT 均无效
- **C 型失败（memory domain）**：需要基础设施或架构改进，SFT 理论上有效但未验证
- **A 型和 B 型失败**：有 prompting 修复潜力，recipe 设计有针对性
- **D 型失败**：验证型 recipe（如 verifier agent）可能有帮助
- **API 方差**（std=0.251 on jx2qv）：评估任何 recipe 效果时需多次运行取均值，<5pp 差异不具解读性
