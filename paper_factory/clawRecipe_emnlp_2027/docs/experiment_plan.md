# 实验计划

## 论文主线

**总主张：Open-source agent failures are often structural, not parametric.**

核心区分：很多 agent failure 不是 model incapability，而是 capability-to-activation gap / state abstraction failure / runtime compatibility issue。修复策略必须按 failure mechanism 选，不是按参数规模。

---

## 核心假设体系（论文脊柱）

| 假设 | 核心主张 | 验证实验 |
|------|---------|---------|
| **H1** | E类失败 = 能力-激活鸿沟（模型"会"但没激活出来），非纯能力不足 | T4(E类) vs 更强checkpoint，若T4接近更强checkpoint则支撑 |
| **H2** | C类失败 = state abstraction failure（不是存不下，是没把状态变成可操作表示） | 结构化state tracker vs 非结构化summary，若远高于后者则支撑 |
| **H3** | A/B/D = 控制闭环断裂（goal grounding → action instantiation → outcome verification） | 断点标注 + planning/preflight/verifier各修复不同断裂段 |
| **H4** | training-free修复结构性失败，SFT修复知识/技能激活失败，二者正交非替代 | category × condition gain matrix，若gain pattern不单调则支撑 |

### 修复配方总览（T1-T4 + SFT）

| 配方 | 针对类别 | 核心机制 | 验证假设 |
|------|---------|---------|---------|
| **T1 (+Memory)** | C | 情景记忆缓冲区（工具调用后写入，新调用前读取） | H2 |
| **T2 (+Control)** | A / B / D | 计划优先 + 前置检查 + 有界重规划 + 失败触发反思 | H3 |
| **T3 (+Collab)** | A / D | 双角色（执行器+验证器），验证器可请求回滚 | H3 |
| **T4 (+Procedure)** | E | T4a程序支持卡片 + T4b技能激活提示 | H1 |
| **SFT-100/300/1000** | E | LoRA-SFT，小数据修正轨迹微调 | H4 |

**更强的总句式**（可写入摘要/引言）：
> Agent failures are often misdiagnosed as model weakness, while many are actually system-level activation, state representation, or runtime compatibility failures.

---

## 团队分工

| 成员 | 负责方向 | 具体任务 |
|------|---------|---------|
| **李佳伟** | H4验证、矩阵整合、论文主笔 | category×condition矩阵、论文整合 |
| **琦崴师弟** | H2/C类、memclawbench构造 | 结构化state tracker实验、memory harness设计、memclawbench构造 |
| **宇航师兄** | SFT实验 | SFT数据构造、SFT微调实验 |
| **玉豪师弟** | E类+procedure harness验证（H1） | E类错误分析、T4 procedure harness实验 |
| **昱辰师兄** | H3验证：A/B/D类全流程 | 对A/B/D类失败轨迹做断点标注（三段：goal grounding/action instantiation/outcome verification）；T2 harness在A/B/D类任务上的修复实验 |
| **王淏师兄** | T3 collab harness验证 | T3 collab harness在A/D类失败任务上的修复实验（辅助H3）；|

---

## 新Benchmark构思

### memclawbench（自构，弥补C类任务稀缺）

**动机**: C类错误仅12条(4%)，因现有benchmark对memory机制要求低。需要构造专门考验memory的任务。

**设计思路**:
- 任务需满足：constraint accumulation、data spread across long context、artifact cross-reference
- 构造多层状态：pending_goals / derived_facts / constraints / artifact_paths
- 只能串行测评：比如解决第6个task可能需要第4个task留下的“记忆”
- 故意让非结构化summary失败，但结构化state tracker能解决
- 参考H2验证命令：constraint-accumulation, data-spreadsheet

**目标**: 构造5-10条高memory需求的C类任务

---

## Phase 1: Baseline 全量实验

### 执行状态

| Benchmark | 任务数 | glm Baseline | 错误分类 | 
|-----------|--------|-------------|---------|
| agentbench-openclaw | 40 | ✅ 75.9 | ✅ 已分类 |
| pinchbench | 23 | ✅ 66.0 | 尚未开始 | 
| clawbench-official | 315 | ✅ 88.1 | ✅ 已分类 | 
| claweval | 199 | ✅ 67.3 | ✅ 已分类 | 
| skillsbench | 87 | ⏳ 差21条 | 尚未开始、skip | 
| zclawbench | 116 | ❌ 未开始 | 尚未开始、skip | 

---

## Phase 2: 错误分类结果 ✅

### 失败分类分布（glm baseline, 300条失败记录，跨agentbench/clawbench/claweval三基准测试）

| 类别 | 数量 | 占比 | 说明 |
|------|------|------|------|
| **A** (任务理解) | 150 | 50% | 最高，需 control harness 修复 |
| **E** (技能利用) | 49 | 16% | 需 procedure harness 修复 |
| **F** (其他) | 82 | 27% | 非agent failure（runtime issue等） |
| **D** (验证) | 44 | 15% | 需 control harness 修复 |
| **B** (工具落地) | 20 | 7% | 需 control harness 修复 |
| **C** (记忆) | 12 | 4% | 需 memory harness 修复 |

### 关键发现 → 支撑假设体系

1. **E类占36%** → 直接支撑 H1（能力-激活鸿沟）
2. **C类持久50.0瓶颈** → 直接支撑 H2（state abstraction failure）
3. **E类vs A/B/D修复机制不同** → 支撑 H4（training-free vs SFT正交）

---

## Phase 3: 假设验证实验

### H1验证：E类 - 能力-激活鸿沟（玉豪负责）

**假设**: E类失败不是"模型不会"，而是"有技能但没激活"

**实验设计**:
- 同一任务比较三种条件：
  1. base
  2. T4（技能激活提示：技能清单+选择检查清单+执行验证）
  3. 更强checkpoint (exp87_ratio5pct_step660)
- 若T4收益接近或超过更强checkpoint，尤其集中在E类 → 支撑H1
- 进一步拆分E类：
  - E1: available-but-unactivated（T4更强）
  - E2: activated-but-miscomposed（SFT更强）

**命令示例**:
```bash
python run.py --bench agentbench --model glm-4.7 --docker --harness procedure \
  --task extract-structured-data,missing-dependency,context-retention,repo-refactor,summary-statistics,no-unnecessary-changes,project-proposal,corrupted-input
```

### H2验证：C类 - State Abstraction Failure（琦崴师弟负责）

**假设**: memory失败不是"存不下"，而是"没有把状态变成decision-relevant表示"

**实验设计**:
- 比较三种memory机制：
  1. 原始长上下文（base）
  2. 非结构化summary memory（T1）
  3. 结构化state tracker（slots: constraints, derived_facts, pending_subgoals, artifact_paths）
- 若3远高于2 → 支撑H2
- 反事实：给oracle memory notes但不改变控制策略，若收益有限 → 进一步支撑"不会用状态"

**命令**:
```bash
python run.py --bench agentbench --model glm --harness memory_structured \
  --task constraint-accumulation,data-spreadsheet
```

### H3验证：A/B/D类 - 控制闭环断裂（昱辰负责断点标注）

**假设**: A/B/D类失败源于goal grounding → action instantiation → outcome verification的闭环断裂

**断点标注说明**: 对每条A/B/D类失败轨迹，人工标注第一个断裂发生在哪一段：
- **A段断裂（goal grounding）**：agent根本没理解对任务目标，执行从一开始就歪了
- **B段断裂（action instantiation）**：agent知道要做什么，但工具/参数/路径落地错了
- **D段断裂（outcome verification）**：agent执行没问题，但错误后没有自我检查和恢复，继续歪

**实验设计**:
- planning修复A段（任务理解）
- preflight修复B段（工具落地）
- verifier修复D段（结果验证）
- 各修复不同断裂段，互相正交


### H4验证：正交修复机制（李佳伟负责）

**假设**: training-free修复结构性失败，A/B/D受益；SFT修复知识/技能激活失败，E类受益；二者正交

**实验设计**:
- 构建category × condition gain matrix：
  - 行：T1/T2/T3/T4/SFT-100/SFT-300
  - 列：A/B/C/D/E
- 预期pattern：
  - T2/T3 在 A/B/D 强
  - T1 在 C 强
  - SFT/T4 在 E 强
- 测组合增益是否接近additive → 支撑"正交修复机制"

---

## Phase 4: Category × Condition 矩阵

### 目标格式

| 条件 | A类 CRR | B类 CRR | C类 CRR | D类 CRR | E类 CRR | Overall | NIR |
|------|---------|---------|---------|---------|---------|---------|-----|
| Base | - | - | - | - | - | - | - |
| +Memory (T1) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| +Control (T2) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| +Collab (T3) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| +Procedure (T4) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| +T5(combo) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| SFT-100 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| SFT-300 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| SFT-1000 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### 验证目标
- H1: T4对E1类修复率高，SFT对E2类修复率高
- H2: 结构化memory对C类远高于非结构化
- H3: planning主要修复A段，preflight修复B段，verifier修复D段
- H4: 矩阵显示非单调替代关系，而是正交修复机制

---

## 实验优先级总结

```
✅ agentbench glm baseline (40 tasks)
✅ agentbench 错误分类 (22 failures, A-E分布清晰)
✅ clawbench glm baseline (315 tasks, 88.1)
✅ claweval glm baseline (199 tasks, 67.3)
⏳ pinchbench glm baseline (23 tasks)
⏳ skillsbench glm baseline 补齐

假设验证优先级:
  [1] H1验证：E类(8条) + procedure harness ← 玉豪
  [2] H2验证：C类(2条) + 结构化memory ← 琦崴师弟
  [3] H3验证：断点标注 ← 昱辰；T2 harness在A/B/D任务上 ← 昱辰/王淏
  [4] H4验证：category×condition矩阵 ← 李佳伟
  [5] memclawbench构造 ← 琦崴师弟（C类任务补充）
  [6] SFT微调 ← 宇航师兄
```

---

## 注意事项

1. **节省成本**: 所有验证实验在错误子集上做，不轻易跑全量
2. **进度可见**: 长时间运行使用 `tee` 记录日志
3. **断点续跑**: 失败任务单独重跑（指定-- task）
4. **可视化**: 每次拿到新结果更新 HTML dashboard
5. **团队协作**: 每周同步实验进展，及时更新矩阵
6. **数据文件**:
   - 错误分类 prompt: `error_analysis/error_classification_prompts.json`
   - 分类结果: `error_analysis/error_classification_prompts_with_category_answered.json`
   - 汇总: `error_analysis/error_classification_summary.csv`
7. **脚本**:run.py;模型统一使用glm-4.7;parallel设为2不容易报api错误;--output-dir设为./
