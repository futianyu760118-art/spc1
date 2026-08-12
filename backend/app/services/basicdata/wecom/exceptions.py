"""企微集成异常体系。"""


class WecomError(Exception):
    """企微集成基类异常。"""


class WecomNotConfiguredError(WecomError):
    """企微凭据未配置。"""


class WecomAPIError(WecomError):
    """企微 API 返回非零 errcode 或 HTTP 错误。"""

    def __init__(self, errcode: int | str, errmsg: str, http_status: int | None = None):
        self.errcode = errcode
        self.errmsg = errmsg
        self.http_status = http_status
        super().__init__(f"[errcode={errcode}] {errmsg}")
