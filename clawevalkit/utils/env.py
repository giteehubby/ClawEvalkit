"""环境变量加载工具。

load_env() 从 .env 文件加载密钥到 os.environ。
这是 clawevalkit.config.load_env() 的底层实现，保留供内部使用。
"""
import os
from pathlib import Path


def load_env(env_file: str = None):
    """加载 .env 文件中的 API 密钥到 os.environ。

    按优先级查找: 参数指定 > 项目根目录/.env
    """
    candidates = []
    if env_file:
        candidates.append(Path(env_file))

    base = Path(__file__).resolve().parent.parent.parent  # ClawEvalKit/
    candidates.append(base / ".env")

    for p in candidates:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
            return str(p)
    return None
