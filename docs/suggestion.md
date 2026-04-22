我觉得你现在最该补的，不是再多做几个普通 ablation，而是提出几条**“如果被验证，就能把论文从经验报告抬升为机制性结论”**的猜想。你现在稿子里已经有几个很好的种子：失败分类 A-E、E 类技能利用、AB-OC 上 memory=50 的结构性瓶颈、以及“训练 free 修复 vs 小数据 SFT”的对照框架。问题在于，当前表述还比较像“我们观察到一些失败，然后设计一些 recipe”，容易被质疑成工程 patchwork。 ￼

我建议你把论文往下面几类猜想上推，每一条都尽量能回答一个更大的问题：agent 的失败到底是能力不足，还是接口/控制结构错配？

⸻

一组最值得做的“大猜想”

1. 很多 agent failure 不是 model incapability，而是 capability-to-activation gap

也就是：模型/系统“会”，但在真实 agent runtime 中激活不出来。

这是你文中最有潜力的一条，因为你已经反复看到 E 类失败：图像生成、PDF 阅读、技能调用，不一定是模型不懂任务，而是没有把已有能力转成正确的 skill activation。你文中已经把 E 类定义为“技能存在但未能有效激活/组合”，这是很好的切口。 ￼

可以把它升级成一个更强的猜想：

Hypothesis H1: 在 open-world agent benchmark 中，相当比例的失败并非来自 base model 缺乏任务知识，而来自能力到调用之间的激活鸿沟；因此，显式 skill activation / affordance prompting 的收益会显著高于增加模型参数或更晚 checkpoint。

这个猜想有价值，因为它会把你的工作从“修 bug”变成在讲一个agent 系统层的基本矛盾。

你可以怎么验：

* 同一任务上比较三种条件：
    1. base
    2. 仅增加“技能清单+选择检查清单+执行后验证”
    3. 更强 checkpoint / 更多 SFT
* 如果 2 的收益接近或超过 3，尤其集中在 E 类，那这个结论就很漂亮。
* 再进一步，把 E 类拆成两种：
    * E1: available-but-unactivated
    * E2: activated-but-miscomposed
* 看 T4b 对 E1 更强，T4a/SFT 对 E2 更强。

这会让你的 E 类不只是“杂项技能问题”，而变成一套更可解释的机制。

⸻

2. memory bottleneck 可能不是“记不住”，而是“不会把 state 变成 decision-relevant representation”

你文中 AB-OC 的 memory 域所有模型都卡在 50.0，非常像结构性瓶颈。这个现象很强，但目前叙述还停留在“存在 C 类失败”。 ￼

更强的猜想应该是：

Hypothesis H2: agent 在 memory tasks 上的主要瓶颈并不是上下文长度或存储容量，而是缺乏对“状态”的显式建模与可操作读取；换言之，失败来自 state abstraction failure，不是单纯的 forgetting。

这个说法比“加记忆 buffer”高级很多，因为它指出：
不是存不下，而是没有把什么该记、怎么取、怎么约束当前动作说清楚。

怎么验：

* 比较三种 memory 机制：
    1. 原始长上下文
    2. 非结构化 summary memory
    3. 结构化 state tracker（例如 slots: constraints, derived facts, pending subgoals, artifact paths）
* 如果 3 远高于 2，就说明问题不是容量，而是表示形式。
* 再做一个 counterfactual：给模型 oracle memory notes，但不改变控制策略；如果收益仍有限，说明问题还包含“不会用状态”。

这条如果做出来，会让你对 C 类的解释更有理论味道。

⸻

3. A/B/D 并不是独立失败，而是同一条“控制闭环断裂”上的不同切面

你现在把 A 任务理解、B 工具落地、D 验证恢复分开是对的，但它们可能还能再上一层抽象：

Hypothesis H3: 很多 agent failures 不是 isolated error types，而是源于同一控制闭环的不同断点：goal grounding → action instantiation → outcome verification。A/B/D 分别对应闭环的三个断裂位置。

这很有研究味，因为它把 taxonomy 从“经验分类”抬升成“控制论视角的 failure pipeline”。

验证方式：

* 对每条失败轨迹标记 first break point：
    * 目标没钉住
    * 动作没落到环境
    * 结果没被检查/纠偏
* 看这些断点是否比 A/B/D label 更稳定、更高一致性。
* 然后测试：
    * planning prompt 主要修复前段断裂
    * preflight/tool grounding 修复中段断裂
    * verifier/reflection 修复后段断裂

如果成立，你论文就能说：
taxonomy 不是 ad hoc，而是对应 agent control loop 的自然分解。

⸻

4. 一部分“规划失败”其实是 runtime artifact induced failure，而不是 reasoning failure

你文中 task_15_daily_summary 的 AGENTS.md / HEARTBEAT.md 污染很有意思，这其实是个非常好的研究点。 ￼

大胆一点，你可以提：

Hypothesis H4: 在真实 agent runtime 中，相当一部分看似“规划/理解错误”的 failure，其实是由环境初始化产物、上下文污染、或 affordance miscue 引发的 artifact-induced misalignment。

这条很新，也比较容易让 reviewer 觉得“哦，这不是简单 benchmark score，而是在揭示 agent runtime 的评估偏差”。

怎么验：

* 对同任务做不同 runtime 条件：
    1. 有 AGENTS.md / SOUL.md / HEARTBEAT.md
    2. 干净 workspace
    3. 这些文件存在但隔离在 metadata channel，不落在工作目录
* 看 A 类失败率是否显著变化。
* 再看强模型是否同样受影响。
    如果强模型也受影响，就说明这不是“弱模型不会做”，而是环境 artifact 在重定向 policy。

这条很值得写，因为它能支撑一个更大的 claim：
benchmark 上测到的不一定是 agent capability，可能是 runtime-ability interaction。

⸻

5. 训练和 training-free 修复解决的是两类本质不同的问题，二者不是强弱关系，而是正交关系

你文中已经隐约这么写了：A-D 更像结构机制问题，E 更像知识/技能利用问题，SFT 与 training-free 是互补。 ￼

我建议把它明确成一条可以被检验的猜想：

Hypothesis H5: training-free interventions primarily repair control-structure failures, while SFT primarily repairs policy priors for skill selection and composition; therefore their gains are orthogonal rather than monotonic substitutes.

这条一旦验证，会很有价值，因为很多人天然以为“能 SFT 就别搞 prompt recipe”。你可以反过来说：
有些失败根本不是权重里学一个模式就能稳修的。

怎么验：

* 做 category-conditioned gain matrix：
    * 行：T1/T2/T3/T4/SFT-100/SFT-300
    * 列：A/B/C/D/E
* 你真正想看到的图像是：
    * T2/T3 在 A/B/D 强
    * T1 在 C 强
    * SFT/T4a 在 E 强
* 再测组合增益是否接近 additive。
    * 如果是，就特别支持“正交修复机制”。

这比单纯报告 overall Δ 更有论文味。

⸻

一组更“脑洞大”、但很可能出彩的猜想

6. agent 的主要问题不是不会搜索，而是不会“终止搜索并提交承诺”

很多 agent 会反复搜、反复试、迟迟不收敛。你 D 类里其实已经碰到这个。 ￼

可以提：

Hypothesis H6: in many benchmark failures, the issue is not insufficient exploration but defective commitment control — agents fail because they cannot decide when evidence is sufficient to stop, verify, and commit.

这条会把 D 类从“没验证”变成更一般的“探索-提交失衡”。

验证：

* 加一个 explicit stopping criterion / sufficiency check
* 测试它是否主要减少：
    * 重复 search
    * 无效重试
    * timeout
* 看它是否对 task_13 / task_20 这类 timeout failure 有帮助

⸻

7. skill-rich environment 反而可能降低成功率，因为它提升了 selection entropy

工具/技能越多，不一定越好；可能让 agent 更难选。你 E 类可以沿这个方向走。

Hypothesis H7: beyond a small set, increasing available skills can hurt performance unless the agent is given explicit selection scaffolds, because tool abundance increases action entropy and distractor affordances.

这个很有意思，也很像 HCI / decision theory 里的 choice overload。

怎么验：

* 同一任务给 agent：
    1. 最小必要工具集
    2. 完整工具集
    3. 完整工具集 + skill activation prompt
* 如果 2 < 1，而 3 回升，就非常漂亮。

这能证明：
问题不是能力少，而是 action space 太宽而没有选择结构。

⸻

8. 一些 benchmark 分数其实在测“runtime compatibility”，不是 agent intelligence

这个和 H4 相关，但更 general。

Hypothesis H8: a non-trivial fraction of benchmark variance is explained by agent-runtime compatibility rather than agent reasoning quality.

你文中已经观察到 PinchBench 同一模型跨运行方差巨大，甚至从 0.058 到 0.847。这个现象非常值得吃透。 ￼

你可以把它做成论文里很有辨识度的一条：

* 比较不同 endpoint / runtime / tool schema / init protocol 的方差
* 分析 variance mostly 来自哪类任务
* 看 high-variance tasks 是否集中于 B/E 类

如果成立，你可以更强地说：
agent benchmark 的 reproducibility 问题，根源之一是 runtime mismatch，而不是 model stochasticity 本身。

⸻

9. 失败分类的“首个断点”比“最终症状”更适合作为监督信号

这个更像方法论贡献。

Hypothesis H9: annotating the earliest causal break in a trajectory yields more predictive and more actionable labels than annotating the final observed failure symptom.

例如一个任务最后表现成 timeout，但根因可能是最早一步 skill misselection。你现在 taxonomy 规则里其实已有“选最早因果链类别”的倾向。 ￼

可以检验：

* 两套标注：
    1. final symptom label
    2. earliest break label
* 看哪套标签更能预测：
    * 哪个 recipe 会修复
    * 是否发生负干扰
* 如果 earliest-break 更好，你的 taxonomy 就更站得住。

⸻

10. 小数据 SFT 的收益可能不是 continuous scaling，而是某些 failure class 上的 phase transition

你文中已经设计 SFT-100/300/1000。与其只是画普通 scaling curve，不如提更强猜想： ￼

Hypothesis H10: SFT does not improve agent performance smoothly across categories; instead, some categories exhibit thresholded gains once the model acquires a reusable procedure schema.

尤其 E 类很像这种：不是多一点点数据就多一点点分，而是“学会某个 procedure 之后突然通了”。

怎么验：

* 按类别画 scaling curve，不看 overall
* 拟合 piecewise / threshold-like curve
* 看 E 类是否存在明显拐点，A/B/C/D 则更平缓或几乎无增益

这会让你的小数据 SFT 部分更有内容，不只是“更多数据更好”。

⸻

如果你想把论文“打成一个更强主线”，我建议优先验证这 4 条

如果资源有限，我最建议优先押这四条：

优先级 1：H1

failure 来自 capability-to-activation gap，而非纯能力不足

优先级 2：H2

memory failure 来自 state abstraction failure，而非简单忘记

优先级 3：H4 / H8

benchmark failure 和方差有相当部分来自 runtime artifact / compatibility

优先级 4：H5

training-free 与 SFT 修复的是正交 failure modes

这四条一旦成立，你论文会从：

* “我们做了个 taxonomy 和一些 recipe”

变成：

* “我们发现 open-source agents 的很多失败不是模型不会，而是系统层激活、状态表示和 runtime 兼容性的问题；因此修复策略必须按 failure mechanism 而不是按参数规模来选。”

这个 statement 就有明显价值了。

⸻

你还可以直接写进 paper 的几个 sharper claim

你现在摘要和引言里可以考虑往这种句式靠：

1. Agent failures are often misdiagnosed as model weakness, while many are actually system-level activation or control failures.  ￼
2. The key distinction is not training-free vs training-based, but structural vs procedural failure.  ￼
3. Memory in agents is not merely storage; it is explicit state representation that must remain decision-relevant across steps.  ￼
4. Benchmark scores for agents partly conflate reasoning ability with runtime compatibility and interface affordances.  ￼

这些句子会让 reviewer 更容易记住你的核心贡献。

⸻

反过来，哪些猜想我觉得不值得投入太多

有几类我觉得会把你带回“普通工程 paper”：

* “再比较更多 prompt wording”
* “再多做几个不同 checkpoint”
* “把 5 类再细分成 9 类，但没有机制解释”
* “只报告 overall score 提升”

这些都容易被问：so what?

你真正需要的是：
哪一种 failure 是由什么机制导致，为什么某一类干预只对它有效。

⸻

我对你这篇论文目前的最大建议

你现在最危险的点不是结果少，而是结论层级偏低。
所以不要急着补很多实验，而是先选 2 到 4 条足够强的 hypothesis，当成论文的 spine。taxonomy、案例、recipe、SFT 全部围着这些 hypothesis 服务。

一个我觉得很适合你的总标题式主张是：

Open-source agent failures are often structural rather than parametric.

然后下面展开：

* E 类：activation gap
* C 类：state abstraction gap
* A/B/D：control-loop breakpoints
* variance：runtime compatibility

这样整篇就会立起来。

如果你愿意，我下一条可以直接帮你把这些脑洞整理成一版论文里的 “Research Questions / Hypotheses” 小节，写成可以直接贴进稿子的学术表述。