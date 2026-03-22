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

## 当前实现

### NanoBotAgent

- 使用 nanobot CLI 的 `agent --message` 命令
- 自动生成 nanobot 配置文件（使用 custom provider）
- 支持单轮和多轮对话
- 从会话文件中提取 transcript 和 usage

### PinchBenchAdapter

- 加载 `tasks/` 目录下的任务文件
- 解析 YAML frontmatter
- 执行 grading 代码进行评分
- 支持 automated / llm / hybrid 评分方式

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
