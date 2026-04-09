# ClawEvalKit 开源宣发文案

---

## 标题方案

**ClawEvalKit: 一个命令，五个 Benchmark，评估任何 Agent**

---

## 正文

### 你还在为 Agent 评测头疼吗？

评估一个 LLM Agent 的能力，往往需要：
- 找到合适的 benchmark 数据集
- 写推理框架对接各种 API
- 搭建沙箱环境跑任务
- 实现评分逻辑
- 每换一个模型就重复一遍以上流程

**ClawEvalKit** 把这些全部统一了。

### 一句话介绍

ClawEvalKit 是一个统一的 Agent 评测框架，用一条命令就能在 5 个主流 Agent Benchmark 上评估任何 OpenAI 兼容模型。

```bash
python3 run.py --bench skillsbench --model claude-sonnet --docker
```

### 覆盖 5 大 Benchmark，295 个任务

| Benchmark | 任务数 | 评测方式 | 能力维度 |
|-----------|-------:|----------|----------|
| **SkillsBench** | 56 | 多轮代码生成 + pytest | 代码编写、环境适配 |
| **AgentBench-OpenClaw** | 40 | 规则评分 + 指标评分 | 文件操作、系统管理 |
| **WildClawBench** | 60 | 自动检查 + LLM Judge | 生产力、编码、社交、搜索、创意、安全 |
| **ZClawBench** | 116 | LLM Judge 四维评分 | 任务完成、工具使用、推理、答案质量 |
| **PinchBench** | 23 | 内嵌评分函数 | 文件操作、内容验证 |

从代码生成到工具使用，从多步推理到安全对齐，ClawEvalKit 覆盖了 Agent 能力评估的核心维度。

### 核心特性

**一条命令，开箱即用**
遵循 VLMEvalKit 的设计理念——单一入口 `run.py`，自包含的 benchmark 类，不用来回切框架。

**YAML 驱动的模型配置**
参考 OpenCompass 风格，加模型只需要创建一个 YAML 文件：

```yaml
my-model:
  name: My Model
  api_url: https://api.example.com/v1
  api_key_env: MY_API_KEY
  model: model-id
  provider: openrouter
```

**Docker 沙箱，完全隔离**
所有 benchmark 任务都在 Docker 容器中执行，保证评测的可复现性和安全性。每个任务独立环境，互不干扰。

**断点续评，增量缓存**
每个任务的结果独立保存，中断后重新运行自动跳过已完成的任务。大规模评测不怕中断。

**并行执行**
通过 `--parallel` 参数，可以同时运行多个任务，充分利用计算资源。

**LLM Judge 自动评分**
支持配置 Judge 模型，自动对 Agent 轨迹进行多维度评分，无需人工标注。

### 快速上手

```bash
# 安装
git clone --recurse-submodules https://github.com/linjh1118/ClawEvalkit.git
cd ClawEvalkit
pip install -e .

# 构建 Docker 镜像
docker build -f Dockerfile.nanobot -t wildclawbench-nanobot:latest .

# 设置 API Key
echo "OPENROUTER_API_KEY=your-key-here" > .env

# 开始评测
python3 run.py --bench skillsbench --model claude-sonnet --docker

# 查看结果
python3 run.py --summary
```

### 适用场景

- **模型开发者**：快速在新模型上跑完整 Agent 评测套件
- **研究人员**：复现和对比不同模型的 Agent 能力
- **竞赛组织者**：搭建标准化的 Agent 评测平台
- **工程师**：CI/CD 中集成 Agent 能力回归测试

### 技术栈

- Python 3.9+
- Docker (所有 benchmark 的执行环境)
- OpenAI 兼容 API (支持 OpenRouter / 直连 / 自建代理)
- NanoBotAgent (统一的 Agent 推理引擎)

---

## 社交媒体短文案

### Twitter/X

ClawEvalKit: evaluate any LLM agent on 5 benchmarks (295 tasks) with a single command. Docker sandboxing, YAML model configs, incremental caching, LLM Judge scoring.

```bash
python3 run.py --bench skillsbench --model claude-sonnet --docker
```

Open source, Apache 2.0.

### 小红书 / 即刻

Agent 评测工具 ClawEvalKit 开源了！一条命令跑 5 个 Benchmark，295 个任务。Docker 沙箱隔离，YAML 配置模型，支持断点续评和并行执行。覆盖代码生成、工具使用、多步推理、安全对齐等核心维度。

### 知乎 / 微信公众号

**ClawEvalKit：让 Agent 评测像跑单元测试一样简单**

做 Agent 评测最痛苦的是什么？是每个 benchmark 都要重新搭一套推理框架、评分逻辑、执行环境。ClawEvalKit 的目标就是把这件事统一成一个命令：`python3 run.py --bench <benchmark> --model <model> --docker`。

我们整合了 5 个主流 Agent Benchmark（SkillsBench、AgentBench-OpenClaw、WildClawBench、ZClawBench、PinchBench），共 295 个评测任务，覆盖代码生成、工具使用、多步推理、安全对齐等 Agent 核心能力维度。

技术上参考了 VLMEvalKit 的单入口设计和 OpenCompass 的 YAML 配置风格，让加模型只需要一个 YAML 文件。所有任务在 Docker 容器中执行，保证可复现性。支持断点续评、并行执行和 LLM Judge 自动评分。

项目已在 GitHub 开源（Apache 2.0 协议），欢迎 Star 和贡献！

---

## GitHub Release Notes 模板

```
## ClawEvalKit v0.1.0 - First Public Release

### Highlights
- Unified evaluation framework for 5 agent benchmarks (295 tasks total)
- Docker sandboxing for reproducible evaluation
- YAML-driven model configuration (OpenCompass style)
- Incremental caching with automatic resume
- Parallel task execution
- LLM Judge scoring support

### Supported Benchmarks
| Benchmark | Tasks | Scoring Method |
|-----------|-------|----------------|
| SkillsBench | 56 | Multi-turn code gen + pytest |
| AgentBench-OpenClaw | 40 | L0 rule + L1 metric |
| WildClawBench | 60 | Automated checks + LLM Judge |
| ZClawBench | 116 | 4-dimension LLM Judge |
| PinchBench | 23 | Embedded grading functions |

### Quick Start
```bash
git clone --recurse-submodules https://github.com/linjh1118/ClawEvalkit.git
cd ClawEvalkit
pip install -e .
docker build -f Dockerfile.nanobot -t wildclawbench-nanobot:latest .
python3 run.py --bench skillsbench --model claude-sonnet --docker
```
```
