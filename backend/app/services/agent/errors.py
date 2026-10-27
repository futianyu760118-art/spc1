"""智能体中心领域错误的公共基类（message + HTTP 语义状态码）。"""


class AgentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
