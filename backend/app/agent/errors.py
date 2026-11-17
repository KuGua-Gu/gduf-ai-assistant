"""Agent 模块异常体系与用户可读的兜底话术。

原则：异常只在后端日志里保留技术细节，返回给用户的一定是能看懂的说明与下一步操作。
"""


class AgentError(Exception):
    """Agent 模块异常基类。"""

    code = "AGENT_ERROR"
    user_message = "我这边出了点小问题，请稍后再试一次。"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.user_message)
        self.detail = detail


class LLMUnavailableError(AgentError):
    """模型接口超时、限流或持续 5xx。"""

    code = "LLM_UNAVAILABLE"
    user_message = "模型服务暂时不可用，请稍等片刻再试；你也可以先在账单页手动记一笔。"


class OutputFormatError(AgentError):
    """模型输出无法解析为约定结构。"""

    code = "OUTPUT_FORMAT_ERROR"
    user_message = "刚才没有理解清楚，可以换成「午饭 25 元」这样的说法再发一次吗？"


class ToolExecutionError(AgentError):
    """工具执行失败（业务层抛错或参数非法）。"""

    code = "TOOL_EXECUTION_ERROR"
    user_message = "数据读写没有成功，这笔记录还没有保存，请稍后重试。"


class ContextOverflowError(AgentError):
    """上下文超出模型窗口上限。"""

    code = "CONTEXT_OVERFLOW"
    user_message = "当前对话太长了，可以点「新会话」后继续，我会保留必要的记账上下文。"


class SafetyViolationError(AgentError):
    """命中越界/高风险请求。"""

    code = "SAFETY_VIOLATION"
    user_message = "这类请求我无法协助。"


# 工具参数连续校验失败后的固定引导文案
TOOL_RETRY_EXCEEDED_MESSAGE = (
    "这条信息我反复理解有偏差，先不写入账本。你可以直接告诉我「金额 + 类别」，"
    "例如「午饭 25 元」，也可以在小票确认页手动填写。"
)
