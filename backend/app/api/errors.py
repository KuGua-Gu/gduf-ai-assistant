"""业务 REST 接口异常。"""

from __future__ import annotations


class BusinessAPIError(Exception):
    """带稳定业务错误码的 API 异常。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
