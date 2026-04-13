# 📄 论文阅读笔记：SKILLFOUNDRY

**论文标题**: SKILLFOUNDRY: Building Self-Evolving Agent Skill Libraries from Heterogeneous Scientific Resources 
**作者机构**: Shuaike Shen 等人，卡内基梅隆大学 (CMU) 

---

## 💡 1. 核心思想 (TL;DR)
目前的大语言模型 (LLM) 智能体在处理真实世界任务时，往往缺乏特定领域的专业知识和程序性常识（即“该怎么做”）。
为了打破这个瓶颈，本文提出了 **SKILLFOUNDRY** 框架。它的使命就是像“炼金术士”一样，把散落在 GitHub、API、文档和论文里的“野生资源”，自动提取、提炼并封装成智能体可以直接使用的、带有说明书和测试用例的“标准化技能包” (Agent Skills) 。最酷的是，它还是一个闭环的自我进化系统 ！

---

## 🛠️ 2. 深入浅出看方法 (Methodology)

这部分的方法论可以说是“顺藤摸瓜”与“优胜劣汰”的完美结合。

### 🌳 核心数据结构：领域知识树 (Domain Knowledge Tree)
系统将目标科学领域表示为一棵有根树 $$T=(V,E)$$ 。
* **节点 (V)**：内部节点代表领域 (Domains) 和子领域 (Subdomains) 。
* **叶子节点**：代表可以执行的技能目标 (Actionable skill targets) 。
* **通俗理解**：这棵树就像是一个“技能科技树”。系统不是像无头苍蝇一样全网乱搜，而是看科技树上哪根树枝“资源丰富但技能缺失”，就优先去哪里“挖矿” 。

### 🔄 自动化“炼丹”循环 (Mining Loop)
整个工作流被抽象为一个流水线：`tree_check -> resource_search -> skill_build -> skill_test -> refresh` 。
1. **资源挖掘 (Resource Mining)**：顺着科技树找靠谱的官方文档、代码库、论文等 。
2. **技能提取 (Skill Extraction)**：把非结构化的文字/代码，变成标准的“技能卡片” (包含输入输出、依赖、代码脚本等) 。
3. **魔鬼测试 (Skill Testing)**：这是把控质量的关键环节 。
 * *执行测试 (Execution Testing)*：测一测这技能到底能不能跑通 。
 * *系统测试 (System Testing)*：针对需要依赖集群（如 SLURM）的高级技能 。
 * *合成数据测试 (Synthetic-data Testing)*：用假的/受控的数据做 Mock 测试，验证它的接口和行为稳定性 。
4. **树的修剪与进化 (Tree Refinement)**：通过了测试的技能会成为新的叶子；如果跟现有的库（如 SkillHub, SkillSMP）撞车了，或者表现太拉胯，就会被无情修剪或合并 。这保证了生成的技能有高达 71.1% 的新颖性 ！

---

## 🔬 3. 实验设置与核心战绩 (Experiments)

作者在实验部分可没有手软，通过基准测试和真实高难度科学任务，证明了 SKILLFOUNDRY 绝对不是花架子。

### 🧪 实验一：MoSciBench (科学发现基准测试)
* **数据与 Benchmark**: 使用包含气候科学、生物医学、地球科学等 6 个数据集的 MoSciBench 。
* **模型/Agent**: 使用基于 Codex 的 Coding Agent 。
* **主要提升**:
 * 给 Agent 装备上 SKILLFOUNDRY 的技能后，在 6 个数据集中有 5 个实现了性能跃升 。
 * Repo-Acc（代码库准确率）从 61.19% 飙升至 66.73% 。
 * Paper-Acc（论文级准确率）从 43.85% 跃升至 53.05% 。
 * **亮点**：代码执行成功率死死钉在 100% ！说明不是单纯代码变容易了，而是科学推理能力变强了 。

### 🧬 实验二：细胞类型注释 (Cell Type Annotation)
* **数据**: 空间转录组数据（人类心脏 MERFISH 数据集，包含 228,635 个细胞） 。
* **模型/对比**: Vanilla Codex vs. Codex + SkillFoundry vs. 领域专用智能体 SpatialAgent 。
* **主要提升**: 
 * 裸奔的 Codex：覆盖率 81.1%，准确率 68.5% 。
 * **Codex + SkillFoundry**：加上临时定制的技能后，覆盖率直逼 99.2%，准确率暴涨至 82.9% ！

### 🧬 实验三：scDRS 工作流 (统计遗传学复杂任务)
* **数据**: TMS FACS 单细胞 RNA-seq 数据 + 审定过的身高 GWAS 数据 。
* **模型/Agent**: 通用生物医学智能体 Biomni 。
* **主要提升**:
 * 这是个高难度的多步统计流程 。
 * 加入 SKILLFOUNDRY 技能后，输出结果与人类专家跑出来的均方根误差 (RMSE) 从 0.11 断崖式降到了 0.02 。
 * 定性评估中，它是**唯一**一个满足了全部 7 项专家评估标准（如正确的 FDR 校正、异质性分析等）的设置 。画出来的图也比“裸奔”的 Biomni 丰富和靠谱得多 。

---

## 🎯 总结
SKILLFOUNDRY 证明了：不需要全部靠人工手写，AI 完全可以通过啃海量的“野生科学资源”，自动组装出一套不仅有效、还自带说明书和测试的强大武器库 。Agentic Science（智能体科学）的时代，指日可待 ！