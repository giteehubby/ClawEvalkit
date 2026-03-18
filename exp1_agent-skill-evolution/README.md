# Agent Skill Self-Evolution

## 项目简介

研究 Agent 如何通过自进化机制动态获取、优化和扩展自身技能（Skill）的系统。

## 目录结构

```
agent-skill-evolution/
├── src/                        # 核心代码
├── assets/
│   ├── logs/                   # 运行日志
│   ├── input/                  # 输入数据
│   └── output/                 # 输出产物
│       ├── benchmarks.json     # Benchmark 调研数据
│       └── benchmarks.html     # Benchmark 可视化界面
├── docs/                       # 文档
├── related_work/               # 调研资料、论文笔记
├── tmp/                        # 临时脚本
└── README.md
```

## 核心研究方向

- **Skill 发现**：Agent 在任务执行中识别可复用的行为模式
- **Skill 抽象**：将具体执行轨迹提炼为通用 Skill 表示
- **Skill 评估**：对生成的 Skill 进行质量评估与筛选
- **Skill 进化**：基于反馈持续优化已有 Skill

## 当前产出

| 文件 | 说明 |
|------|------|
| `assets/output/benchmarks.json` | 15 个 benchmark 的结构化调研数据 |
| `assets/output/benchmarks.html` | 可交互可视化界面（含筛选、搜索、图表） |

---

## 实验推进历程

### Round 1 — Benchmark 调研（2026-03-18）

**设计动机**

在开始系统设计前，先摸清该领域已有哪些评测基准，了解各方向的任务设计、评估指标和核心发现，为后续实验选型提供依据。

**具体方案与关键参数**

- 来源：用户指定的微信文章（含 SkillsBench、SE-Bench 等）+ 网络搜索补充
- 覆盖方向：Skill 评估、自进化、终身学习、软件工程、工具使用、真实任务、多模态
- 数据结构：每条记录含 name、year、arxiv、institution、tasks、domains、key_findings、tags

**结果数据**

- 共整理 15 个 benchmark
- 时间跨度：2024–2025
- 总任务数：6,000+
- 产出文件：`assets/output/benchmarks.json`、`assets/output/benchmarks.html`

**核心发现**

- Skill 评估方向：SkillsBench 发现 curated skills +16.2pp，但 self-generated skills 无效甚至负向
- 自进化方向：SE-Bench 用 obfuscated API 强制测试真实知识内化，揭示 context-use ≠ learning
- 软件工程方向：Multi-SWE-Bench（2132 tasks，8语言）和 SWE-Bench Pro（1865 tasks）是最大规模基准
- 真实任务方向：GDPval-AA 覆盖 44 职业、9 行业，是最贴近经济价值的评测
- CASCADE 在 SciSkillBench 上通过累积 skill 进化将成功率从 35.4% 提升至 93.3%（+57.9pp）

**推导出的下一步洞察**

- self-generated skills 普遍无效，说明 skill 质量控制是核心瓶颈
- 终身学习（StuLife、Evo-Memory）和 skill 生态（AgentSkillOS）是相对空白的方向
- 下一步可选：(1) 复现 CASCADE 的累积 skill 创建机制；(2) 针对 SkillsBench 设计 skill 自进化方案
