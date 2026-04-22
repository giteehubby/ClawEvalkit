# Proofread Report — clawRecipe EMNLP 2027
Date: 2026-03-27

## 错误详细分类

---

## 一、阻断性错误（Critical — 会导致拒稿或严重误导审稿人）

### 1. LaTeX 编译错误

| 文件 | 问题 | 严重程度 |
|------|------|----------|
| `main.tex` | `acl_natbib.bst` 不在 TeX 搜索路径中，导致 `\bibliographystyle{acl_natbib}` 找不到样式文件，**所有引用全部失效**，PDF 中显示 `[?]` | 阻断性 — 引用全废 |
| 已修复 | 将 `acl_natbib.bst` 复制到 paper 根目录，编译通过 | |

### 2. 未定义引用（Undefined References）

| 引用键 | 出现位置 | 影响 |
|--------|----------|------|
| `\ref{sec:exp:dev}` | `harness.tex:46`（+BestTrainFree 条件描述） | 编译警告，PDF 中显示 `??` |
| `\ref{sec:exp:dev}` | `recipes.tex:90`（T5 combined recipe） | 同上 |
| `\ref{sec:exp:dev}` | `sft.tex:19`（train/dev/test 分离描述） | 同上 |
| `\ref{tab:main-results}` | `appendix.tex:4`（per-benchmark 表格说明） | 同上 |
| 已全部修复 | 将 `\ref{dev}` 改为文字描述，移除不存在的 `\ref{tab:main-results}` | |

### 3. 事实性错误（Factual Error）

| 文件:行 | 错误内容 | 正确内容 |
|----------|----------|----------|
| `sft.tex:17` | "We use the **OpenClaw-7B** base model" | "We use the **doubao-seed-1.8** base model" — 实验全程使用的都是 doubao-seed-1.8，OpenClaw-7B 是另一个模型 |
| 已修复 | | |

### 4. 过度声明（Overclaiming — 与实验事实不符）

| 文件:位置 | 错误声明 | 问题 |
|-----------|----------|------|
| `abstract.tex` | "we **evaluate** four classes of lightweight training-free recipes and find that their effectiveness is highly failure-type-dependent" | T1-T5 **从未实际运行**，全部标记为 `[Planned]`，"evaluate" 和 "find" 是已完成时态，实际没有结果 |
| `related.tex:9` | "validated with inter-annotator agreement"（描述 taxonomy 已验证） | taxonomy **未经过正式标注**，limitation 中明确说 "informal annotation"，inter-annotator agreement 是计划中而非已完成 |
| 已修复 abstract | 改为 "we **design** four classes...and provide a **preliminary analysis** of their expected effectiveness" | |
| 已修复 related | 改为 "validated through a **planned** inter-annotator agreement study" | |

---

## 二、逻辑/结构性错误（Major — 明显影响论文质量）

### 5. 引用目标丢失

| 问题 | 描述 |
|------|------|
| `\ref{tab:main-results}` 不存在 | appendix.tex 引用了一个在论文中从未定义的表格（main-results），实际存在的是 `tab:pinchbench-results` 和 `tab:agentbench-results` |
| `sec:exp:dev` 不存在 | recipes/sft/harness 中引用了一个从未定义的章节（dev split evaluation），但实验部分从未设计 dev split 协议 |
| 已修复 | |

### 6. Citation Key 不匹配

| 文本中使用 | bib 文件中的 key | 结果 |
|------------|------------------|------|
| `\citep{zhou2024}` | `zhou2024data`（第137条） | BibTeX 找不到匹配，编译警告 `[zhou2024]` undefined |
| 已修复 | 改为 `\citep{zhou2024data}` | |

### 7. Bib 条目未使用（14个）

以下 bib 条目存在于 `refs/references.bib` 中，但论文正文从未引用：

| Citation Key | 条目标题 | 备注 |
|--------------|----------|------|
| `landis1977measurement` | The Measurement of Observer Agreement for Categorical Data | 只在 appendix 中提到 Cohen's κ，但没有用 `\citep{}` |
| `mialon2023gaia` | GAIA: A Benchmark for General AI Assistants | 完全未引用 |
| `browsecomp2025` | BrowseComp: A Multi-Hop Web Browsing Benchmark | 完全未引用 |
| `phan2025hle` | Humanity's Last Exam | 完全未引用 |
| `xbench2025` | XBench: A Multi-Horizon Benchmark for RAG | 完全未引用 |
| `webwalkerqa2025` | WebWalkerQA: Benchmarking LLM Agents | 完全未引用 |
| `offseeker2026` | OffSeeker: Aligning Open-Source LLMs | 完全未引用 |
| `li2026cso` | Critical Step Identification for Agent Preference Learning | 完全未引用 |
| `shi2024dmpo` | Direct Multi-Turn Preference Optimization | 完全未引用 |
| `rosenbaum2024credits` | Credit Assignment in Multi-Step Agent Trajectories | 完全未引用 |
| `liu2023benchmarking` | Benchmarking General-Purpose AI Agents | related.tex 第5行使用了 `\citep{liu2023benchmarking}`，但编译时也报 undefined → 说明该 key 在 bib 中存在但未被正确解析（需检查） |
| 建议 | 删除未使用的条目，或在正文合适位置补充引用 | 审稿人可能会质疑为什么列了这些参考文献却没有引用 |

### 8. 表格数据描述歧义

| 文件:行 | 问题 | 修复建议 |
|---------|------|----------|
| `experiments.tex:13` 表脚注 | 脚注说 "High-Failure Tasks" = scoring below 0.5，但 memory domain 显示 "50.0% (all models)"，50.0 是绝对分数不是失败率，% 符号造成歧义 | 已改为 "Low-scoring tasks...structural outlier scoring exactly 50.0"，去掉了 "High-Failure" 标签 |

### 9. PinchBench 表格 task ID 疑似重复

| 问题 | 分析 |
|------|------|
| 表格中有 `task_16_email_triage` 和 `task_16_market_research` 两个 task 都用 task_16 | 原始数据确认真实存在：`task_16_email_triage` 和 `task_16_market_research` 并存于 PinchBench v0.9，PinchBench 的 task ID 编号不是严格连续的 **不是论文错误**，但建议在表格注释中注明 |

---

## 三、表达/风格问题（Minor — 写作质量提升）

### 10. 短语歧义

| 文件:行 | 问题 | 建议 |
|---------|------|------|
| `harness.tex:17` | "Tasks average 6--10 steps with multiple tool calls" — "multiple" 太模糊 | 改为 "2--5 tool calls per step" 或量化 "multiple (2--5) tool calls" |

### 11. Related Work 句式不流畅

| 文件:行 | 问题 | 建议 |
|---------|------|------|
| `related.tex:5` | "The closest prior work is \citet{zeng2024token}..." — "is + citation" 结构读起来不自然 | 改为 "The closest prior work addresses step-level credit assignment in DPO \citep{zeng2024token}..." |

### 12. Introduction 措辞过于确定

| 文件:行 | 问题 | 建议 |
|---------|------|------|
| `introduction.tex:30` | "We provide empirical evidence that E-type failures..." — 基于 4--5 个 failure cases 就说 "empirical evidence" 可能被审稿人质疑统计显著性 | 加 "preliminary"： "from our preliminary case study analysis" |

### 13. SFT setup 缺失 [Planned] 标记

| 文件:行 | 问题 |
|---------|------|
| `sft.tex` 整体 | recipes.tex 和 abstract 都有 `[Planned; not yet experimentally evaluated]` 诚实声明，但 sft.tex 的研究问题部分没有。读者可能会误以为 SFT 实验已完成。 |

---

## 四、LaTeX 格式警告（非阻断，但影响美观）

| 警告类型 | 位置 | 说明 |
|----------|------|------|
| Underfull `\hbox` (badness 3492) | `conclusion.tex:33` | 段落排版有空行/多余空格 |
| Underfull `\hbox` (badness 2343) | `main.bbl:50` (参考文献) | 参考文献 bbl 文件中的排版问题 |
| UTF-8 invalid byte | `acl.sty` 的 lineno 宏包 | acl.sty 中有非 UTF-8 字符，不影响 PDF 输出 |

---

## 五、修复状态总览

| 错误ID | 类型 | 严重程度 | 状态 |
|--------|------|----------|------|
| 1. bst 文件缺失 | 阻断性 | Critical | ✅ 已修复 |
| 2. 未定义引用（4处） | 阻断性 | Critical | ✅ 已修复 |
| 3. OpenClaw-7B 写错 | 事实性 | Critical | ✅ 已修复 |
| 4. Abstract overclaim | Overclaiming | Critical | ✅ 已修复 |
| 5. related.tex overclaim | Overclaiming | Critical | ✅ 已修复 |
| 6. citation key 不匹配 | 引用 | Major | ✅ 已修复 |
| 7. bib 未使用（14条） | 引用 | Major | ⚠️ 需手动处理 |
| 8. 表格脚注歧义 | 歧义 | Major | ✅ 已修复 |
| 9. task ID 重复 | 数据 | Minor | ✅ 确认非论文错误 |
| 10. "multiple tool calls" 歧义 | 表达 | Minor | ⚠️ 待修复 |
| 11. related 句式不流畅 | 表达 | Minor | ⚠️ 待修复 |
| 12. "empirical evidence" 措辞 | 表达 | Minor | ⚠️ 待修复 |
| 13. SFT 缺 [Planned] 标记 | 诚实性 | Minor | ⚠️ 待修复 |

**建议优先级**：先处理 #7（删除未使用的 bib 条目），再处理 #10-13（写作风格改进），最后做一轮完整编译检查。
