# ClawEvalKit Implementation Schedule

## Context
目标：将 WildClawBench 和 SkillsBench 集成到 ClawEvalKit 统一评测框架中，使用 NanoBotAgent 作为推理引擎。

支持两种模式：
- **Native 模式** (`use_docker=False`): 使用 NanoBotAgent 在宿主机直接运行
- **Docker NanoBotAgent 模式** (`use_docker=True`): 在 Docker 容器内运行 NanoBotAgent，通过卷挂载实现开发迭代

---

## 已完成 ✅

### WildClawBench

- [x] **Native 模式 (`wildclawbench.py`)**:
  - 支持全部 6 个类别（60 tasks）
  - 使用 task parser 提取 prompt、workspace path、automated checks
  - 添加 `ensure_agent_browser()` 检测/安装函数
  - 使用 temp dir + symlink 实现 workspace 隔离
  - Skills 作为 system prompt 注入

- [x] **添加 `run_automated_checks` 函数**:
  - 在 `wildclawbench_grading.py` 中实现
  - 直接在宿主机运行 Python grading 代码
  - 处理 /tmp_workspace 路径映射

- [x] **更新 `grading/__init__.py`**:
  - 导出 `run_automated_checks` 函数

- [x] **Docker NanoBotAgent 模式**:
  - 创建 `Dockerfile.nanobot`: 基于 `wildclawbench-ubuntu:v1.2`，安装 openclawpro
  - 新增 `_evaluate_docker_nanobot()` 方法: 在容器内执行 NanoBotAgent
  - 支持卷挂载 `OpenClawPro/` 实现代码热更新（不用 rebuild 镜像）
  - `evaluate()` 方法新增 `use_nanobot_in_docker` 和 `openclawpro_dir` 参数

- [x] **代码验证**:
  - 模块导入正常
  - 60 tasks 全部加载正确
  - 自动化 checks 测试通过

- [x] **结果缓存与 collect() 修复**:
  - `collect()` 方法同时支持 native 和 docker_nanobot 结果路径
  - 新增 `_collect_from_native_dir()` 和 `_collect_from_docker_dir()` 辅助方法
  - Docker 模式增加 per-task 去重（检查 `{task_id}.json` 是否存在）
  - 成功结果自动保存到 dedup 文件供后续缓存检测
  - `passed` 字段重命名为 `scored` 避免语义歧义（实际含义是"获得有效分数的任务数"）

### SkillsBench

- [x] **Per-task Docker 模式 (`skillsbench.py`)**:
  - 新增 `_evaluate_docker()` 方法: 每个任务用自己的 Dockerfile 构建镜像
  - 容器内运行 NanoBotAgent + pytest 多轮验证
  - 挂载 OpenClawPro 实现代码热更新
  - 新增 `SKIP_TASKS_DOCKER` 集合: Docker 模式下仍需跳过的任务
  - 复用 WildClawBench 的容器管理逻辑

- [x] **Docker 执行流程**:
  1. 遍历所有任务（排除 SKIP_TASKS_DOCKER）
  2. 对每个任务: `docker build -t task-{name}` → `docker run` → `docker exec` NanoBotAgent
  3. pytest 验证 → 反馈修正（最多 max_turns 轮）
  4. 收集结果并清理容器/镜像

### AgentBench

- [x] **AgentBench Docker 模式**:
  - 40 任务支持
  - Docker 容器内运行 NanoBotAgent
  - 使用 volume mount 挂载 OpenClawPro 和 workspace
  - 支持 parallel 并行执行

---

## 数据下载状态 ⚠️

## Context
目标：将 WildClawBench 集成到 ClawEvalKit 统一评测框架中，使用 NanoBotAgent 作为推理引擎。

支持两种模式：
- **Native 模式** (`use_docker=False`): 使用 NanoBotAgent 在宿主机直接运行
- **Docker NanoBotAgent 模式** (`use_docker=True, use_nanobot_in_docker=True`): 在 Docker 容器内运行 NanoBotAgent，通过卷挂载实现开发迭代

## 已完成 ✅

- [x] **Native 模式 (`wildclawbench.py`)**:
  - 支持全部 6 个类别（60 tasks）
  - 使用 task parser 提取 prompt、workspace path、automated checks
  - 添加 `ensure_agent_browser()` 检测/安装函数
  - 使用 temp dir + symlink 实现 workspace 隔离
  - Skills 作为 system prompt 注入

- [x] **添加 `run_automated_checks` 函数**:
  - 在 `wildclawbench_grading.py` 中实现
  - 直接在宿主机运行 Python grading 代码
  - 处理 /tmp_workspace 路径映射

- [x] **更新 `grading/__init__.py`**:
  - 导出 `run_automated_checks` 函数

- [x] **Docker NanoBotAgent 模式**:
  - 创建 `Dockerfile.nanobot`: 基于 `wildclawbench-ubuntu:v1.2`，安装 openclawpro
  - 新增 `_evaluate_docker_nanobot()` 方法: 在容器内执行 NanoBotAgent
  - 支持卷挂载 `OpenClawPro/` 实现代码热更新（不用 rebuild 镜像）
  - `evaluate()` 方法新增 `use_nanobot_in_docker` 和 `openclawpro_dir` 参数

- [x] **代码验证**:
  - 模块导入正常
  - 60 tasks 全部加载正确
  - 自动化 checks 测试通过

## 数据下载状态 ⚠️

### 问题
HuggingFace 在中国大陆访问受限，workspace 数据下载不完整（部分目录为空）。

### 已下载
- 01_Productivity_Flow: 837MB
- 02_Code_Intelligence: 5MB
- 03_Social_Interaction: 288KB
- 04_Search_Retrieval: 3.9MB
- 05_Creative_Synthesis: 19MB
- 06_Safety_Alignment: 33MB

### 待完成
需要完整下载 workspace 数据（建议使用 VPN 或代理）:

```bash
cd /Volumes/F/Clauding/ClawEvalkit/benchmarks/wildclawbench

# 方法1: 使用 VPN/代理
huggingface-cli download internlm/WildClawBench workspace --repo-type dataset --local-dir . --local-dir-use-symlinks False

# 方法2: 使用 hf 库
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('internlm/WildClawBench', repo_type='dataset', local_dir='.', ignore_patterns=['Images/**'])
"
```

### 预处理（如需要完整数据）
```bash
cd /Volumes/F/Clauding/ClawEvalkit/benchmarks/wildclawbench
bash script/prepare.sh
```
需要工具: yt-dlp, ffmpeg, gdown, modelscope

## 运行测试

```bash
cd /Volumes/F/Clauding/ClawEvalkit

# 列出所有 benchmark
python run.py --list

# === WildClawBench ===

# Native 模式测试（默认）
python run.py --bench wildclawbench --model claude-sonnet --sample 1

# Docker NanoBotAgent 模式测试
python run.py --bench wildclawbench --model claude-sonnet --sample 1 --docker

# === SkillsBench ===

# Native 模式测试
python run.py --bench skillsbench --model gemini-3-flash-preview --sample 1

# Docker per-task 模式测试
python run.py --bench skillsbench --model gemini-3-flash-preview --sample 1 --docker

# === AgentBench ===

# Native 模式测试
python run.py --bench agentbench --model minimax-m2.7 --sample 1

# Docker 模式测试
python run.py --bench agentbench --model minimax-m2.7 --sample 1 --docker
```

## Docker NanoBotAgent 模式使用指南

### 构建镜像

```bash
cd /Volumes/F/Clauding/ClawEvalkit
docker build -f Dockerfile.nanobot -t wildclawbench-nanobot:latest .
```

### 验证热更新

修改 `OpenClawPro/harness/agent/memory/store.py` 中的日志，重新跑任务，确认日志变化（不用 rebuild）。

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DOCKER_IMAGE_NANOBOT` | NanoBotAgent Docker 镜像名 | `wildclawbench-nanobot:latest` |
| `OPENCLAWPRO_DIR` | OpenClawPro 源码目录 | `ClawEvalkit/OpenClawPro` |
| `OPENROUTER_API_KEY` | LLM API Key | - |

---

## AgentBench

- [x] **AgentBench Docker 模式 (`agentbench.py`)**:
  - 支持 40 个任务
  - 新增 `_evaluate_docker()` 方法: 在容器内执行 NanoBotAgent
  - 复用 WildClawBench 的容器管理逻辑
  - 支持并行执行 (`parallel` 参数)
  - `evaluate()` 方法支持 `use_docker` 参数

- [x] **AgentBench 局限性**:
  - 评分仅基于文件存在性 (L0)，不支持 L1/L2/L3 评分
  - 部分任务（如 `impossible-request`）没有 expected_outputs，依赖 expected_behavior 验证
  - 当前实现对这些任务返回 0 分

---

## SkillsBench Docker Per-task 模式

### 工作原理

每个 SkillsBench 任务都有自己的 `environment/Dockerfile`，定义了任务所需的环境依赖。

```
task/
├── instruction.md      # 任务描述
├── environment/
│   ├── Dockerfile     # 任务专用镜像构建文件
│   ├── skills/        # 可选的 skills
│   └── ...            # 其他依赖文件
└── tests/
    └── test_outputs.py
```

### Docker 执行流程

```bash
# 1. 构建 per-task 镜像
docker build -t skillsbench-task-{task_name} -f task/environment/Dockerfile task/environment/

# 2. 启动容器（挂载 OpenClawPro + workspace）
#    注意：mount 点根据任务路径模式动态选择（见下文路径映射）
docker run -d --name {container} \
  -v /tmp/skillsbench_workspace:{mount_point}:rw \
  -v /path/to/OpenClawPro:/root/OpenClawPro:rw \
  skillsbench-task-{task_name}

# 3. 容器内执行 NanoBotAgent
docker exec {container} python3 /tmp/exec_nanobot.py

# 4. pytest 验证
docker exec {container} python3 -m pytest {mount_point}/tests/test_outputs.py

# 5. 清理
docker rm -f {container}
docker rmi skillsbench-task-{task_name}
```

### 路径映射（Path Mapping）

不同任务使用不同的路径模式，需要动态处理：

| 路径模式 | 示例任务 | Mount 点 | 符号链接 |
|---------|---------|---------|---------|
| `/root/input/` + `/root/output/` | edit-pdf | `/workspace` | `/root/input` → `{mount}/input` |
| `/workspace/` | spring-boot-jakarta-migration | `/workspace` | 无 |
| `/app/workspace/` | flink-query, lean4-proof | `/app/workspace` | 无 |
| `/root/workspace/` | parallel-tfidf-search | `/workspace` | 无 |

**动态检测逻辑**：
- 检测 `instruction.md` 中的路径引用
- `/app/workspace/` 任务：mount at `/app/workspace`
- 其他任务：mount at `/workspace`
- 需要 `/root/input/` 或 `/root/output/` 时创建相应符号链接

### SKIP_TASKS vs SKIP_TASKS_DOCKER

| 集合 | 说明 | 不使用 Docker | 使用 Docker |
|------|------|:---:|:---:|
| `SKIP_TASKS` | 需要 Docker 或特殊依赖的任务 | 跳过 | 正常运行 |
| `SKIP_TASKS_DOCKER` | 即使 Docker 也无法运行的任务 | 跳过 | 跳过 |

### 注意事项

- **镜像构建时间**: 每个任务都要 `docker build`，可用 `docker buildx` 缓存层优化
- **磁盘空间**: 任务完成后自动删除镜像 `docker rmi`
- **构建失败**: 任务标记为 `skipped`，不影响其他任务

---

## PinchBench Docker 模式

- [x] **PinchBench Docker 模式 (`pinchbench.py`)**:
  - 支持 23 个任务
  - 新增 `_evaluate_docker()` 方法: 在容器内执行 NanoBotAgent
  - 复用 WildClawBench 的 `wildclawbench-nanobot:v3` 镜像
  - 支持并行执行 (`parallel` 参数)
  - `evaluate()` 方法支持 `use_docker` 参数
  - 支持内嵌 `grade()` 函数在容器中执行评分

### 使用方式

```bash
cd /Volumes/F/Clauding/ClawEvalkit

# Native 模式测试（默认）
python run.py --bench pinchbench --model claude-sonnet --sample 1

# Docker 模式测试
python run.py --bench pinchbench --model claude-sonnet --sample 1 --docker

# Docker 并行模式
python run.py --bench pinchbench --model claude-sonnet --sample 5 --docker --parallel 2
```

### 测试脚本

```bash
cd /Volumes/F/Clauding/ClawEvalkit/benchmarks/pinchbench/scripts

# 测试单个任务
python test_docker.py --sample 1

# 测试多个任务并行
python test_docker.py --sample 3 --parallel 2
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PINCHBENCH_DOCKER_IMAGE` | Docker 镜像名 | `wildclawbench-nanobot:v3` |
| `OPENCLAWPRO_DIR` | OpenClawPro 源码目录 | `ClawEvalkit/OpenClawPro` |
| `OPENROUTER_API_KEY` | LLM API Key | - |

---

## `--harness` CLI 参数支持

### 概述

在 `run.py` CLI 层面添加了 `--harness` 参数，使 NanoBotAgent 在评测时可以启用对应的增强能力（recipe）。

### 支持的 recipe

| recipe | config 类 | 说明 |
|--------|-----------|------|
| `memory` | `MemoryConfig(enabled=True)` | 记忆增强 |
| `control` | `ControlConfig(enabled=True)` | 流程控制增强 |
| `collaboration` | `CollabConfig(enabled=True)` | 多智能体协作 |
| `procedure` | `ProceduralConfig(enabled=True)` | 程序化增强（需 skill card） |

### 修改的文件

| 文件 | 修改内容 |
|------|---------|
| `run.py` | 添加 `--harness` CLI 参数；指定时默认 `output-dir=outputs/harness/{recipe}` |
| `clawevalkit/inference.py` | 新增 `get_harness_config()` 辅助函数；提取 harness 并转为 agent config |
| `clawevalkit/dataset/_harness.py` | 新增共享工具函数 `build_harness_script_parts()`，统一处理 harness → exec-script 的 import/kwargs 映射 |
| `agentbench.py` | `_build_exec_script()` 使用 `build_harness_script_parts()` |
| `wildclawbench.py` | 同上 |
| `zclawbench.py` | 同上 |
| `tribe.py` | 同上 |
| `pinchbench.py` | 同上 |
| `clawbench_official.py` | 同上 |
| `skillsbench.py` | `_run_single_task()` 和 `_run_agent_in_container()` 支持 harness；native + docker 模式均支持 |
| `claweval.py` | `_run_single_task()` 支持 harness |

### Bug 修复

- **`collab` vs `collaboration` 模块路径**: `get_harness_config("collaboration")` 返回 key 为 `collab_config`，但 `_build_exec_script()` 中 `replace('_config','')` 生成 `harness.agent.collab` 是错的（正确路径是 `harness.agent.collaboration`）。修复方式：在 `_harness.py` 中用 `HARNESS_MODULE_MAP` 显式映射 `collab_config → harness.agent.collaboration`，不再依赖字符串替换。

### 使用方式

```bash
# 验证参数解析
python run.py --list --harness collaboration

# 带 harness 运行 agentbench (Docker 模式)
python run.py --bench agentbench --harness collaboration --sample 10 --docker \
  --output-dir outputs/harness/collaboration

# 带 harness 运行 skillsbench (native 模式)
python run.py --bench skillsbench --harness memory --sample 5
```

### 注意事项

- **procedure** recipe 需要 skill card YAML/JSON 文件（`cards_dir`），目前仓库中无 skill card，加载 0 张卡片，recipe 可运行但无实际效果
- **control** Config 没有 `to_dict()` / `from_dict()` 方法，但 Docker exec-script 直接构造 Python 代码字符串，不受影响
- 所有 benchmark 的 `evaluate()` 均能接受未知的 kwargs（大多数已有 `**kwargs`），`harness_config` 从中 pop 出来使用

### 测试验证 ✅

| Harness | Benchmark | 模式 | 结果 |
|---------|-----------|------|------|
| `memory` | agentbench | Docker, 2 samples | ✅ 通过 |
| `collaboration` | agentbench | Docker, 2 samples | ✅ 通过（修复 `collab` → `collaboration` 后通过）|
| `control` | agentbench | Docker, 2 samples | ✅ 通过 |
