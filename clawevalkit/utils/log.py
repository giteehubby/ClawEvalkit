"""日志工具。"""
from datetime import datetime
import logging


def log(msg: str):
    """实时日志输出（带时间戳）。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def setup_logging(verbose: bool = False):
    """配置 logging 以显示 NanoBotAgent 内部日志。

    Args:
        verbose: 如果为 True，显示 DEBUG 级别日志
    """
    level = logging.DEBUG if verbose else logging.INFO

    # 配置 root logger (统一输出，避免重复)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # 清除已有的 handlers，避免重复输出
    root_logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(name)s] %(message)s', datefmt='%H:%M:%S'))
    root_logger.addHandler(handler)

    # 配置所有相关子 logger (propagate=True 默认会将日志传到 root logger)
    for logger_name in [
        'nanobot', 'harness', 'agent', 'clawevalkit',
        'clawevalkit.dataset', 'clawevalkit.utils', 'clawevalkit.dataset.wildclawbench'
    ]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        # 不再添加独立 handler，让日志传播到 root logger 统一输出
        logger.propagate = True
