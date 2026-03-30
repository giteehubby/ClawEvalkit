"""
ZClawBench 任务加载器。

从 HuggingFace (zai-org/ZClawBench) 加载任务。
每个任务有一个 task_id 和一个初始 prompt (第一条 user 消息)。
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zclawbench.task_loader")

# ---------------------------------------------------------------------------
# ZClawBench 六大类 (与 ClawBench 体系对齐)
# ---------------------------------------------------------------------------
CATEGORIES = [
    "Office & Daily Tasks",
    "Automation",
    "Information Search & Gathering",
    "Development & Operations",
    "Security",
    "Data Analysis",
]


@dataclass
class ZClawBenchTask:
    """ZClawBench 任务对象"""
    task_id: str
    name: str
    category: str
    prompt: str          # 第一条 user 消息作为任务描述
    timeout_seconds: int = 300
    workspace_path: str = "/tmp/zclawbench_workspace"
    # 原始轨迹信息（用于离线分析）
    reference_trajectories: Dict[str, List[Dict]] = field(default_factory=dict)
    # 可用工具列表（从轨迹中提取）
    tool_names: List[str] = field(default_factory=list)

    @classmethod
    def from_hf_row(cls, row: Dict[str, Any]) -> "ZClawBenchTask":
        """从 HuggingFace dataset row 构建任务对象"""
        # trajectory 是 JSON 字符串，需要解析
        traj_str = row.get("trajectory", "[]")
        try:
            traj = json.loads(traj_str) if isinstance(traj_str, str) else traj_str
        except Exception:
            traj = []

        # 提取第一条 user 消息作为 prompt
        prompt = ""
        for msg in traj:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            prompt = c.get("text", "")
                            break
                break

        # 提取使用的工具列表
        tool_names = set()
        for msg in traj:
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_use":
                            tool_names.add(c.get("name", "?"))

        task_id = row.get("task_id", "")
        model_name = row.get("model_name", "")
        category = row.get("task_category", "unknown")

        return cls(
            task_id=task_id,
            name=task_id,  # ZClawBench 没有独立 name，用 task_id
            category=category,
            prompt=prompt,
            timeout_seconds=300,
            workspace_path=f"/tmp/zclawbench_workspace/{task_id}",
            reference_trajectories={model_name: traj},
            tool_names=list(tool_names),
        )


class ZClawBenchTaskLoader:
    """从 HuggingFace 加载 ZClawBench 任务"""

    def __init__(self, dataset_name: str = "zai-org/ZClawBench"):
        self.dataset_name = dataset_name
        self._tasks: Dict[str, ZClawBenchTask] = {}
        self._loaded = False

    def load_all_tasks(
        self,
        category: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> List[ZClawBenchTask]:
        """加载所有任务（按 task_id 去重）

        Args:
            category: 可选，筛选特定类别
            model_name: 可选，筛选特定模型的轨迹（仅影响 reference_trajectories）
        """
        self._ensure_loaded()

        tasks = []
        seen = set()
        for task_id, task in self._tasks.items():
            if category and task.category != category:
                continue
            if task_id not in seen:
                seen.add(task_id)
                tasks.append(task)

        logger.info(f"Loaded {len(tasks)} unique tasks (category={category or 'all'})")
        return tasks

    def load_all_trajectories(
        self,
        category: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> Dict[str, Dict[str, List[Dict]]]:
        """加载所有轨迹（按 task_id × model 组织）

        Returns:
            {task_id: {model_name: trajectory}}
        """
        self._ensure_loaded()

        result: Dict[str, Dict[str, List[Dict]]] = {}
        for task_id, task in self._tasks.items():
            if category and task.category != category:
                continue
            if task_id not in result:
                result[task_id] = {}
            # 合并 reference_trajectories
            for m, traj in task.reference_trajectories.items():
                if model_name is None or model_name.lower() in m.lower():
                    result[task_id][m] = traj

        return result

    def _ensure_loaded(self) -> None:
        """懒加载 HuggingFace 数据集"""
        if self._loaded:
            return

        try:
            from datasets import load_dataset
        except ImportError:
            logger.error("datasets library not installed. Run: pip install datasets")
            raise

        logger.info(f"Loading ZClawBench from HuggingFace: {self.dataset_name}")
        ds = load_dataset(self.dataset_name, split="train")
        logger.info(f"Loaded {len(ds)} rows (116 tasks × 6 models)")

        # 按 task_id 分组合并
        task_map: Dict[str, ZClawBenchTask] = {}
        for row in ds:
            task = ZClawBenchTask.from_hf_row(dict(row))
            if task.task_id not in task_map:
                task_map[task.task_id] = task
            else:
                # 合并 reference_trajectories（同一个 task_id 不同 model）
                existing = task_map[task.task_id]
                for m, traj in task.reference_trajectories.items():
                    existing.reference_trajectories[m] = traj
                # 合并工具列表
                for t in task.tool_names:
                    if t not in existing.tool_names:
                        existing.tool_names.append(t)

        self._tasks = task_map
        self._loaded = True
        logger.info(f"Parsed {len(self._tasks)} unique tasks")
