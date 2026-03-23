# 统一评估框架设计文档

## 目标

使用统一的 Agent 推理框架（nanobot）运行多个 benchmark 的测评，通过简单的命令行参数配置即可开始测试。

## 核心设计

### 1. 统一 Agent 接口 (BaseAgent)

定义 `BaseAgent` 抽象基类，所有 Agent 实现都需实现以下接口：

```python
class BaseAgent(ABC):
    def __init__(self, model, api_url, api_key, workspace, timeout):
        pass

    def execute(self, prompt: str, session_id: str = None) -> AgentResult:
        """执行单个 prompt"""
        pass

    def execute_multi(self, prompts: List[str], session_id: str = None) -> List[AgentResult]:
        """执行多轮对话"""
        pass
```

### 2. Benchmark 适配器模式

每个 Benchmark 有自己的适配器，负责：

- 加载任务（从 benchmark 的 tasks/ 目录）
- 解析任务格式
- 评分逻辑
- 结果报告

适配器调用统一的 Agent 接口，与具体的 Agent 实现解耦。

### 3. 命令行入口

通过 `scripts/run.py` 统一入口，用户只需提供：

- `--benchmark`: 选择 benchmark
- `--api-url`: API 基础 URL
- `--api-key`: API 密钥
- `--model`: 模型 ID

## 测试命令

### PinchBench (23 个任务)

```bash
cd work/benchmarks/scripts

# 运行全部任务
python run.py --benchmark pinchbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key <your-api-key> \
    --model gpt-4o-mini

# 运行特定任务
python run.py --benchmark pinchbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key <your-api-key> \
    --model gpt-4o-mini \
    --tasks task_00_sanity,task_01_calendar,task_04_weather

# 运行 fast 测试（5个任务）
python test_run.py
```

### OpenClawBench (40 个任务，7 个 suite)

```bash
cd work/benchmarks/scripts

# 运行全部任务
python run.py --benchmark openclawbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key <your-api-key> \
    --model gpt-4o-mini

# 运行特定 suite
python run.py --benchmark openclawbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key <your-api-key> \
    --model gpt-4o-mini \
    --suite research

# 运行 fast 测试（easy + medium 难度）
python run.py --benchmark openclawbench \
    --api-url https://openrouter.ai/api/v1 \
    --api-key <your-api-key> \
    --model gpt-4o-mini \
    --difficulty fast

# 运行 OpenClawBench 快速验证
python test_openclawbench.py
```

## 当前实现

### NanoBotAgent

- 使用 litellm 直接调用 LLM API
- 支持 tool calling（read_file, write_file, edit_file, list_dir, exec, web_search, web_fetch）
- 兼容 pinchbench grading 代码的 transcript 格式

### PinchBenchAdapter

- 加载 `pinchbench/tasks/` 目录下的任务文件
- 解析 YAML frontmatter
- 执行任务内嵌的 grading 代码进行评分
- 支持 automated / llm / hybrid 评分方式

### OpenClawBenchAdapter

- 加载 `agentbench-openclaw/tasks/` 目录下的 task.yaml 文件
- 四层评分体系：L0(结构检查) / L1(指标分析) / L2(行为分析) / L3(输出质量)
- 自动复制输入文件，运行 setup.sh 脚本
- 支持 suite 和 difficulty 筛选

## 运行流程

1. 解析命令行参数
2. 创建 Agent 实例（nanobot/openclaw）
3. 创建 Benchmark 适配器
4. 加载任务列表
5. 逐个运行任务：
   - 准备工作空间
   - 调用 Agent 执行
   - 评分
6. 生成报告

## 扩展计划

1. 实现 OpenClaw Agent 适配器
2. 添加更多 Benchmark 适配器
3. 支持分布式运行
4. 生成 HTML 可视化报告
