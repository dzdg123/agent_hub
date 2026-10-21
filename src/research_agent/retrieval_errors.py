"""检索运行故障的显式边界；数据、配置和程序错误不在此白名单中。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator


class RetrievalOperationalError(RuntimeError):
    """协调层唯一捕获的可降级故障，保留底层错误类型和操作名称。"""

    def __init__(self, message: str, *, operation: str | None = None,
                 error_type: str | None = None) -> None:
        super().__init__(message)
        self.operation = operation
        self.error_type = error_type or type(self).__name__


@contextmanager
def operational_boundary(
    operation: str, *, expected_errors: tuple[type[Exception], ...] = (),
) -> Iterator[None]:
    """只包裹具体模型/库调用；不包裹参数、向量或来源数据校验。"""
    try:
        yield
    except (OSError, *expected_errors) as exc:
        raise RetrievalOperationalError(
            f"{operation} 未就绪：{exc}", operation=operation,
            error_type=type(exc).__name__,
        ) from exc
    except sqlite3.OperationalError as exc:
        # 只接受忙碌/锁竞争，SQL 错误、损坏和未知数据库故障原样抛出。
        code = getattr(exc, "sqlite_errorcode", None)
        if code is None or code & 0xFF not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise
        raise RetrievalOperationalError(
            f"{operation} 未就绪：{exc}", operation=operation,
            error_type=type(exc).__name__,
        ) from exc
