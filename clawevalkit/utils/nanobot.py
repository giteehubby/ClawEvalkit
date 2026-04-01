"""共享的 NanoBotAgent 导入工具。

所有需要 NanoBotAgent 的 benchmark 模块都从这里导入，避免重复代码。
搜索优先级：pip 包 → OPENCLAWPRO_DIR 环境变量 → 仓库内 OpenClawPro/ 子目录。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def import_nanobot_agent():
    """延迟导入 NanoBotAgent，按优先级搜索可用路径。

    搜索顺序:
    1. 已安装的 openclawpro pip 包
    2. OPENCLAWPRO_DIR 环境变量指向的目录
    3. 仓库根目录下的 OpenClawPro/ 子目录

    Returns:
        NanoBotAgent 类

    Raises:
        ImportError: 所有路径都找不到 NanoBotAgent
    """
    try:
        from openclawpro.harness.agent import NanoBotAgent
        return NanoBotAgent
    except ImportError:
        pass

    candidates = [
        os.getenv("OPENCLAWPRO_DIR"),
        str(Path(__file__).parent.parent.parent / "OpenClawPro"),
    ]
    for path_str in candidates:
        if not path_str:
            continue
        p = Path(path_str)
        if (p / "harness" / "agent" / "nanobot.py").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            from harness.agent.nanobot import NanoBotAgent
            return NanoBotAgent

    raise ImportError(
        "NanoBotAgent not found. Install OpenClawPro or set OPENCLAWPRO_DIR env var.\n"
        "  pip install openclawpro   OR   export OPENCLAWPRO_DIR=/path/to/OpenClawPro"
    )
