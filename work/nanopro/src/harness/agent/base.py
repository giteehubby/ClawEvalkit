"""
统一 Agent 接口定义。

所有 Agent 适配器（nanobot、openclaw 等）都需实现此接口。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentResult:
    """Agent 执行结果"""

    def __init__(
        self,
        status: str,
        content: str = "",
        transcript: List[Dict[str, Any]] | None = None,
        usage: Dict[str, Any] | None = None,
        workspace: str = "",
        execution_time: float = 0.0,
        error: str = "",
    ):
        self.status = status  # success, error, timeout
        self.content = content
        self.transcript = transcript or []
        self.usage = usage or {}
        self.workspace = workspace
        self.execution_time = execution_time
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "content": self.content,
            "transcript": self.transcript,
            "usage": self.usage,
            "workspace": self.workspace,
            "execution_time": self.execution_time,
            "error": self.error,
        }

    def save_transcript(self, path: Path | str) -> None:
        """保存 transcript 到 JSONL 文件

        Args:
            path: 保存路径（.jsonl 文件）
        """
        import json
        import logging
        logger = logging.getLogger("agent.result")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not self.transcript:
            logger.warning(f"save_transcript called with empty transcript for {path.name}")

        with open(path, "w", encoding="utf-8") as f:
            for entry in self.transcript:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        actual_lines = len(self.transcript)
        logger.info(f"Saved transcript: {path.name} ({actual_lines} entries)")

    def save_result(self, path: Path | str) -> None:
        """保存完整结果到 JSON 文件

        Args:
            path: 保存路径（.json 文件）
        """
        import json
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


class BaseAgent(ABC):
    """Agent 抽象基类"""

    @abstractmethod
    def __init__(
        self,
        model: str,
        api_url: str,
        api_key: str,
        workspace: Path,
        timeout: int = 300,
        **kwargs,
    ):
        """初始化 Agent

        Args:
            model: 模型 ID (如 anthropic/claude-sonnet-4)
            api_url: API 基础 URL
            api_key: API 密钥
            workspace: 工作目录
            timeout: 超时时间（秒）
        """
        pass

    @abstractmethod
    def execute(self, prompt: str, session_id: str | None = None) -> AgentResult:
        """执行单个 prompt

        Args:
            prompt: 用户输入
            session_id: 会话 ID（用于多轮对话）

        Returns:
            AgentResult: 执行结果
        """
        pass

    @abstractmethod
    def execute_multi(
        self, prompts: List[str | Dict[str, Any]], session_id: str | None = None
    ) -> List[AgentResult]:
        """执行多轮对话

        Args:
            prompts: 多个 prompt 列表，支持纯字符串或带元数据的 session dict
            session_id: 会话 ID

        Returns:
            List[AgentResult]: 每个 prompt 的执行结果
        """
        pass

    def cleanup(self) -> None:
        """清理资源（如会话文件）"""
        pass
