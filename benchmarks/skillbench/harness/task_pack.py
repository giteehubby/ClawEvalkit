from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import List, Optional

import yaml


@dataclass
class TaskSpec:
    id: str
    path: Optional[str]
    repo_path: Optional[str]
    instructions: Optional[str]


@dataclass
class TaskPack:
    name: str
    version: str
    description: str
    tasks: List[TaskSpec]
    manifest_path: pathlib.Path


def load_task_pack(pack_path: pathlib.Path) -> TaskPack:
    manifest = pack_path / "manifest.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    tasks = [
        TaskSpec(
            id=str(task.get("id")),
            path=task.get("path"),
            repo_path=task.get("repo_path"),
            instructions=task.get("instructions"),
        )
        for task in data.get("tasks", [])
    ]
    return TaskPack(
        name=str(data.get("name")),
        version=str(data.get("version")),
        description=str(data.get("description", "")),
        tasks=tasks,
        manifest_path=manifest,
    )
