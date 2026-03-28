# NanoPro Developer Guide

## 项目概述

NanoPro 是一个统一的 Agent 评估框架，基于 NanoBot Agent 实现了 5 种 training-free recipes (T1-T5)，可以运行多个 benchmark 进行评估。

### 项目结构

```
work/nanopro/
├── nanobot/                    # NanoBot Agent 核心代码
├── src/
│   ├── harness/agent/          # Agent 适配器层
│   │   ├── nanobot.py          # NanoBotAgent 主实现
│   │   ├── base.py             # BaseAgent 抽象基类
│   │   ├── memory/             # T1: Memory 模块
│   │   ├── control/            # T2: Control 模块
│   │   ├── collaboration/      # T3: Collaboration 模块
│   │   └── procedure/          # T4: Procedure 模块
│   ├── runners/adapters/       # Benchmark 适配器
│   └── conditions/             # 统一导出
├── scripts/
│   └── run.py                  # 统一入口
└── benchmarks/                 # 测试任务
```

---

## Training-Free Recipes (T1-T5)

### T1: Memory (Episodic Memory)
**作用**: 帮助 Agent 记住工具执行结果和错误

**核心类**:
- `MemoryConfig` - 配置
- `EpisodicMemoryStore` - 存储管理
- `WritePolicy` / `RetrievalPolicy` - 写入/检索策略

**CLI Flags**:
```bash
--memory-enabled
--memory-max-items 20
--memory-write-policy tool_result_or_error
--memory-retrieval-policy recent
```

### T2: Control (Single-agent Control)
**作用**: 提供计划生成、重规划、失败反思、预检、重试等控制机制

**核心类**:
- `ControlConfig` - 总配置
- `PlanFirst` - 任务开始前生成计划
- `ReplanTrigger` - 检测需要重新规划的信号
- `FailureReflection` - 失败后反思
- `PreflightCheck` - 工具调用前检查
- `RetryPolicy` - 失败重试

**CLI Flags**:
```bash
--control-enabled
--plan-first-enabled
--replan-enabled
--retry-enabled
--reflection-enabled
--preflight-enabled
```

### T3: Collaboration (Minimal Two-agent)
**作用**: 轻量级多 Agent 协作 (planner-executor 或 executor-verifier)

**核心类**:
- `CollabConfig` - 配置
- `PlannerRole` - 生成执行计划
- `ExecutorRole` - 执行计划步骤
- `VerifierRole` - 检验执行结果
- `HandoffManager` - 角色间交接管理

**CLI Flags**:
```bash
--collab-enabled
--collab-mode planner_executor  # 或 executor_verifier
--collab-critique-frequency on_error  # on_error / every_step / never
--collab-max-handoffs 3
```

### T4: Procedure (Procedural Support)
**作用**: 紧凑的技能卡片，按需展开到 prompt 中

**核心类**:
- `ProceduralConfig` - 配置
- `SkillCard` - 技能卡片 (name, description, trigger_keywords, steps, examples)
- `ProceduralStore` - 卡片存储 (从 YAML/JSON 加载)
- `ProceduralTrigger` - 关键词匹配触发
- `ProceduralExpander` - 格式化卡片内容

**CLI Flags**:
```bash
--procedural-enabled
--procedural-cards-dir /path/to/cards  # 包含 YAML/JSON 卡片的目录
--procedural-max-expansions 3
```

**SkillCard 示例** (`my_skill.yaml`):
```yaml
name: file_search
description: Search for files matching a pattern
trigger_keywords: [search, find, locate]
steps:
  - "Use grep or find command to locate files"
  - "Filter results by pattern"
  - "Return matching file paths"
examples:
  - "Find all Python files in src/"
```

### T5: Memory + Control
**作用**: T1 + T2 组合

**CLI Flags**:
```bash
--recipe-t5  # 等价于 --memory-enabled --control-enabled --plan-first-enabled --replan-enabled --reflection-enabled
```

---

## 如何开发新的模块

### 1. 创建模块目录

假设要添加新的 recipe "T6: Custom"，创建:

```
src/harness/agent/custom/
├── __init__.py
├── config.py
├── main.py
└── event.py
```

### 2. 实现配置类

```python
# config.py
from dataclasses import dataclass

@dataclass
class CustomConfig:
    enabled: bool = False
    option_a: str = "default"
    option_b: int = 10
```

### 3. 实现核心逻辑

```python
# main.py
class CustomModule:
    def __init__(self, config: CustomConfig, agent):
        self.config = config
        self.agent = agent

    async def process(self, context):
        # 核心逻辑
        pass
```

### 4. 导出接口

```python
# __init__.py
from .config import CustomConfig
from .main import CustomModule

__all__ = ["CustomConfig", "CustomModule"]
```

### 5. 集成到 NanoBotAgent

在 `nanobot.py` 中:

```python
# __init__ 中添加
self._custom_config = custom_config or CustomConfig(enabled=False)
self._init_custom_modules()

# 新增初始化方法
def _init_custom_modules(self):
    if not self._custom_config.enabled:
        return
    self._custom_module = CustomModule(self._custom_config, self)

# _run_loop 中集成
# 在适当位置调用 self._custom_module.process(...)

# execute 中重置和记录
if self._custom_config.enabled:
    self._custom_module.reset()  # 重置状态
    # 记录 summary
```

### 6. 添加 CLI 参数

在 `scripts/run.py` 中:

```python
# 添加 builder
def build_custom_config(args):
    if not getattr(args, 'custom_enabled', False):
        return None
    return CustomConfig(
        enabled=True,
        option_a=getattr(args, 'custom_option_a', 'default'),
    )

# create_agent 添加参数
def create_agent(..., custom_config=None, ...):
    # pass to NanoBotAgent
    return NanoBotAgent(..., custom_config=custom_config, ...)

# 添加 argparse 参数
parser.add_argument("--custom-enabled", action="store_true")
parser.add_argument("--custom-option-a", type=str, default="default")

# create_agent 调用处添加
create_agent(..., custom_config=build_custom_config(args), ...)
```

---

## 运行测试

### 基本运行

```bash
cd /Volumes/F/Clauding/AwesomeSkill/work/nanopro/scripts

# 运行 pinchbench
python run.py --benchmark pinchbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key YOUR_KEY \
    --model anthropic/claude-sonnet-4-20250514

# 只运行特定任务
python run.py --benchmark pinchbench --tasks task_01_calendar,task_02_stock

# 并行运行
python run.py --benchmark skillsbench --threads 10
```

### 启用 Recipes

```bash
# 只启用 T1 (Memory)
python run.py --benchmark pinchbench --memory-enabled

# 只启用 T2 (Control)
python run.py --benchmark pinchbench --control-enabled --plan-first-enabled

# 启用 T3 (Collaboration)
python run.py --benchmark pinchbench --collab-enabled --collab-mode planner_executor

# 启用 T4 (Procedure)
python run.py --benchmark pinchbench --procedural-enabled --procedural-cards-dir ./my_cards

# 启用 T5 (Memory + Control)
python run.py --benchmark pinchbench --recipe-t5

# 组合多个
python run.py --benchmark pinchbench \
    --memory-enabled \
    --control-enabled --plan-first-enabled \
    --collab-enabled \
    --procedural-enabled --procedural-cards-dir ./cards
```

### Smoke Test

```bash
# 运行 2-task 子集快速验证
python run.py --benchmark pinchbench --tasks task_01_calendar,task_02_stock --smoke
```

---

## 模块总结方法

每个模块应提供 `get_xxx_summary()` 函数，记录到 transcript:

```python
def get_custom_summary(module):
    return {
        "enabled": True,
        "processed_count": module.counter,
        "option_a": module.config.option_a,
    }
```

---

## 代码风格

1. **保持简洁**: 不要过度封装，逻辑清晰即可
2. **添加断点**: 长时间循环添加进度提示
3. **异步优先**: 使用 `async/await` 处理 LLM 调用
4. **日志记录**: 使用 `self._logger.info/debug()` 记录关键事件

---

## 参考资料

- 完整进度: `docs/experiment/schedule.md`
- 示例实现: `src/harness/agent/memory/` 和 `src/harness/agent/control/`
