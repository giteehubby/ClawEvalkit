"""通用重试工具"""
from __future__ import annotations

import subprocess
import time
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar('T')


def with_retry(max_retries: int = 3, base_delay: float = 1.0) -> Callable:
    """通用重试装饰器，支持指数退避。

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒），每次重试翻倍

    Returns:
        装饰后的函数，失败时返回 None

    Example:
        @with_retry(max_retries=3, base_delay=1.0)
        def run_command(cmd: list) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, timeout=30)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T | None]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T | None:
            last_error = None
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    # 对于 subprocess，返回码 0 表示成功
                    if isinstance(result, subprocess.CompletedProcess):
                        if result.returncode == 0:
                            return result
                    elif isinstance(result, bool):
                        if result:
                            return result
                    else:
                        return result
                except subprocess.TimeoutExpired as e:
                    last_error = e
                except Exception as e:
                    last_error = e
                    if attempt == max_retries - 1:
                        raise

                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt))

            return None
        return wrapper
    return decorator
