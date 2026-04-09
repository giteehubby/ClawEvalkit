---
license: mit
task_categories:
- visual-question-answering
- image-text-to-text
- question-answering
language:
- en
- zh
tags:
- agents
- benchmark
- evaluation
- openclaw
- multi-modal
size_categories:
- n<1K
---


<p align="center">
  <img src="https://huggingface.co/datasets/internlm/WildClawBench/resolve/main/assets/lobster_battle.png" alt="WildClawBench Lobster" width="480">
</p>
<p align="center">
  <b>Hard, practical, end-to-end evaluation for AI agents — in the wild.</b>
</p>

<div align="center">

[![Leaderboard](https://img.shields.io/badge/🏆_Leaderboard-WildClawBench-8c2416)](https://internlm.github.io/WildClawBench/)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-5865F2?logo=github&logoColor=white)](https://github.com/InternLM/WildClawBench)
[![HuggingFace](https://img.shields.io/badge/🤗_HuggingFace-Dataset-yellow)](https://huggingface.co/datasets/internlm/WildClawBench)
[![Tasks](https://img.shields.io/badge/Tasks-60-blue)]()
[![Models](https://img.shields.io/badge/Models-10-green)]()

</div>

## 📌 Overview


**WildClawBench** is an agent benchmark that tests what actually matters: can an AI agent do real work, end-to-end, without hand-holding?

We drop agents into a live [OpenClaw](https://github.com/openclaw/openclaw) environment — the same open-source personal AI assistant that real users rely on daily — and throw **60 original tasks** at them: clipping goal highlights from a football match, negotiating meeting times over multi-round emails, hunting down contradictions in search results, writing inference scripts for undocumented codebases, catching privacy leaks before they happen. Useful things. Hard things.

Hard enough that **every frontier model today scores below 0.6**. That makes scores mean something.

## 📂 Repository Contents

This Hugging Face repository hosts the heavy assets required to run the benchmark:

* **`Images/wildclawbench-ubuntu_v1.2.tar`**: The official Docker image containing the isolated Ubuntu environment, OpenClaw instance, and all necessary tools (browser, bash, file system).
* **`workspace/`**: The task data directory containing initial and evaluation files for all 60 tasks.

## 📊 Benchmark Structure

The benchmark covers 6 categories across English and Chinese:

| Category | Tasks | Key Challenges |
|:---------|:---:|:---------------|
| **Productivity Flow** | 10 | Information synthesis, multi-source aggregation, and structured output. |
| **Code Intelligence** | 12 | Undocumented codebase comprehension and pixel-level visual reasoning. |
| **Social Interaction** | 6 | Multi-turn communication, API orchestration, and context tracking. |
| **Search & Retrieval** | 11 | Web search + local data reconciliation and source verification. |
| **Creative Synthesis** | 11 | Video/audio processing and cross-modal generation (e.g., match highlights). |
| **Safety Alignment** | 10 | Adversarial robustness, credential awareness, and harmful content refusal. |

### What Sets Us Apart

- **Real environment, not mocks.** Tasks run inside a live OpenClaw instance with real tools (browser, bash, file system, email, calendar).
- **60 original tasks, built by hand.** Not adapted from existing benchmarks — each task was designed from scratch to stress-test real-world agent capabilities.
- **Reproducible & isolated.** Each task runs in its own Docker container. Same image, same data, same grading code. Ground truth and grading scripts are injected only after the agent finishes — they are never visible during execution, eliminating data leakage. Scores are reproducible across machines.


## Quick Start

### Install Docker

<details>
<summary>macOS</summary>

```bash
brew install --cask docker
```

After installation, launch Docker Desktop from Applications or run:

```bash
open -a Docker
```

</details>

<details>
<summary>Ubuntu</summary>

```bash
# Install dependencies
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add apt repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Allow current user to run Docker without sudo
sudo usermod -aG docker $USER
newgrp docker
```

</details>

### Download Image

Download the Docker image tarball from [HuggingFace](https://huggingface.co/datasets/internlm/WildClawBench/blob/main/Images/wildclawbench-ubuntu_v1.2.tar):

```bash
pip install -U huggingface_hub
huggingface-cli download internlm/WildClawBench Images/wildclawbench-ubuntu_v1.2.tar --repo-type dataset --local-dir .
```

Then load the image:

```bash
docker load -i Images/wildclawbench-ubuntu_v1.2.tar
```

### Download Task Data

Download the task data from [HuggingFace](https://huggingface.co/datasets/internlm/WildClawBench/tree/main/workspace):

```bash
huggingface-cli download internlm/WildClawBench workspace --repo-type dataset --local-dir .
```


## Contributors

[Shuangrui Ding](https://mark12ding.github.io/)\* (Project Lead), [Xuanlang Dai](https://github.com/LennoxDai)\*, [Long Xing](https://github.com/Cooperx521)\*, [Shengyuan Ding](https://github.com/SYuan03), [Ziyu Liu](https://liuziyu77.github.io/), [Jingyi Yang](https://yjyddq.github.io/), [Penghui Yang](https://github.com/yph22), [Zhixiong Zhang](https://github.com/rookiexiong7), [Xilin Wei](https://github.com/wiselnn570)

Advisors: [Yubo Ma](https://mayubo2333.github.io/), [Haodong Duan](https://kennymckormick.github.io/), [Jing Shao](https://amandajshao.github.io/), [Jiaqi Wang](https://myownskyw7.github.io/), [Dahua Lin](http://dahualin.org/), [Kai Chen](https://chenkai.site/), [Yuhang Zang](https://yuhangzang.github.io/)


## Acknowledgements

WildClawBench builds on top of the excellent open-source agent ecosystem. We gratefully acknowledge the following projects:

- **[OpenClaw](https://github.com/openclaw/openclaw)** 
- **[Claw-Eval](https://github.com/claw-eval/claw-eval)**
- **[PinchBench](https://github.com/pinchbench/skill)** 

---