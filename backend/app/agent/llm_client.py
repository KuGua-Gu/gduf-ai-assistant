"""LLM 客户端：用 OpenAI 兼容协议统一接入 DeepSeek / 智谱 GLM / 通义千问。

设计要点：
- base_url / api_key / model 全部来自 Settings，切换供应商只改环境变量；
- SDK 自带重试关闭（max_retries=0），只对超时、连接失败、429、5xx 做指数退避重试；
- 不向调用方暴露 SDK 细节，异常统一转换为 LLMUnavailableError / OutputFormatError；
- 每次调用累计 token 用量并记录结构化日志，日志中 API Key 一律脱敏。
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

from pydantic import BaseModel, Field

from app.agent.errors import LLMUnavailableError, OutputFormatError
from app.config import Settings, get_settings

logger = logging.getLogger("app.agent.llm")

# json 修复重试时回填给模型的引导语
_JSON_REPAIR_PROMPT = "上一次输出不是合法 JSON，请只输出 JSON 对象，不要解释："
# 修复重试时保留的上一次输出长度上限
_MAX_REPAIR_CONTENT = 1000
# 解析失败的哨兵值（与 JSON null 区分）
_JSON_MISS = object()


class ToolCall(BaseModel):
    """模型发起的一次工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any]  # 已 json.loads 的实参；解析失败时置 {}


class LLMResponse(BaseModel):
    """一次 chat 调用的归一化结果。"""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, int] = Field(default_factory=dict)  # prompt/completion/total_tokens


class LLMClient:
    """OpenAI 兼容协议的同步客户端，供 orchestrator 直接调用。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化客户端；SDK 实例延迟到首次调用时创建，避免未配置 Key 时报错。"""
        self._settings = settings if settings is not None else get_settings()
        self._client: Any | None = None
        self._usage_totals: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @property
    def configured(self) -> bool:
        """是否已配置可用的 API Key。"""
        return self._settings.llm_configured

    @property
    def usage_totals(self) -> dict[str, int]:
        """返回累计 token 用量的副本，调用方可安全修改。"""
        return dict(self._usage_totals)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> LLMResponse:
        """调用模型并返回归一化结果。

        参数：
            messages: OpenAI 格式的消息列表。
            tools: 工具定义；非空时启用 tool_choice="auto"。
            temperature: 采样温度。
            json_mode: 是否要求模型输出 JSON 对象；供应商不支持时自动去掉该参数重试一次。

        异常：
            LLMUnavailableError: 未配置 Key、参数错误、限流/超时/5xx 重试耗尽。
        """
        client = self._ensure_client()
        try:
            import openai  # 延迟导入，未安装时由 _ensure_client 给出明确提示
        except ImportError as exc:  # pragma: no cover - 依赖缺失属部署问题
            raise LLMUnavailableError("未安装 openai SDK，请先执行 pip install -u openai") from exc

        max_retries = max(0, int(self._settings.llm_max_retries))
        retries_used = 0
        json_mode_dropped = False
        started_at = time.perf_counter()

        while True:
            kwargs: dict[str, Any] = {
                "model": self._settings.llm_model,
                "messages": messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if json_mode and not json_mode_dropped:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                completion = client.chat.completions.create(**kwargs)
                break
            except openai.BadRequestError as exc:
                # 部分供应商不支持 response_format，去掉该参数再试一次
                if json_mode and not json_mode_dropped:
                    json_mode_dropped = True
                    logger.warning(
                        "模型 %s 不支持 response_format=json_object，去掉该参数后重试",
                        self._settings.llm_model,
                    )
                    continue
                raise LLMUnavailableError(
                    detail=self._describe_error(exc, "模型接口参数错误")
                ) from exc
            except (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError) as exc:
                if retries_used >= max_retries:
                    raise LLMUnavailableError(
                        detail=self._describe_error(exc, f"模型接口重试 {retries_used} 次后仍失败")
                    ) from exc
                delay = 0.5 * (2**retries_used) + random.uniform(0.0, 0.3)
                retries_used += 1
                logger.warning(
                    "模型调用失败（%s），%.2fs 后进行第 %d 次重试",
                    type(exc).__name__,
                    delay,
                    retries_used,
                )
                time.sleep(delay)
            except openai.APIStatusError as exc:
                status = int(getattr(exc, "status_code", 0) or 0)
                if status >= 500:
                    if retries_used >= max_retries:
                        raise LLMUnavailableError(
                            detail=self._describe_error(
                                exc, f"模型接口重试 {retries_used} 次后仍失败"
                            )
                        ) from exc
                    delay = 0.5 * (2**retries_used) + random.uniform(0.0, 0.3)
                    retries_used += 1
                    logger.warning(
                        "模型接口返回 %d，%.2fs 后进行第 %d 次重试",
                        status,
                        delay,
                        retries_used,
                    )
                    time.sleep(delay)
                    continue
                # 4xx 参数/鉴权错误不重试
                raise LLMUnavailableError(
                    detail=self._describe_error(exc, "模型接口请求被拒绝")
                ) from exc

        response = self._to_response(completion)
        self._accumulate_usage(response.usage)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "llm chat model=%s elapsed_ms=%.0f prompt_tokens=%d completion_tokens=%d "
            "total_tokens=%d finish_reason=%s retries=%d json_mode=%s api_key=%s",
            self._settings.llm_model,
            elapsed_ms,
            response.usage.get("prompt_tokens", 0),
            response.usage.get("completion_tokens", 0),
            response.usage.get("total_tokens", 0),
            response.finish_reason or "-",
            retries_used,
            "on" if json_mode and not json_mode_dropped else "off",
            self._mask_key(self._settings.llm_api_key),
        )
        return response

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """要求模型输出 JSON 对象并解析为 dict。

        首次解析失败时追加一条修复提示重试一次；仍失败抛 OutputFormatError。
        模型返回 JSON 数组时包装为 {"items": [...]}。
        """
        response = self.chat(messages, temperature=temperature, json_mode=True)
        parsed = self._parse_json(response.content)

        if parsed is _JSON_MISS:
            repair_messages = [
                *messages,
                {
                    "role": "user",
                    "content": _JSON_REPAIR_PROMPT + response.content[:_MAX_REPAIR_CONTENT],
                },
            ]
            logger.warning("chat_json 首次输出不是合法 JSON，追加修复提示重试一次")
            repaired = self.chat(repair_messages, temperature=temperature, json_mode=True)
            parsed = self._parse_json(repaired.content)
            if parsed is _JSON_MISS:
                raise OutputFormatError(
                    detail=f"模型输出无法解析为 JSON：{repaired.content[:200]}"
                )

        if isinstance(parsed, list):
            return {"items": parsed}
        if isinstance(parsed, dict):
            return parsed
        raise OutputFormatError(detail=f"模型返回的 JSON 不是对象：{str(parsed)[:200]}")

    # ---------- 内部工具 ----------

    def _ensure_client(self) -> Any:
        """校验配置并创建（或复用）OpenAI 客户端。"""
        if not self.configured:
            raise LLMUnavailableError("未配置 LLM_API_KEY")
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - 依赖缺失属部署问题
                raise LLMUnavailableError(
                    "未安装 openai SDK，请先执行 pip install -u openai"
                ) from exc
            self._client = OpenAI(
                base_url=self._settings.llm_base_url,
                api_key=self._settings.llm_api_key,
                timeout=self._settings.llm_timeout_seconds,
                max_retries=0,
            )
        return self._client

    def _to_response(self, completion: Any) -> LLMResponse:
        """把 SDK 的 ChatCompletion 转成 LLMResponse。"""
        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise LLMUnavailableError("模型返回了空结果（choices 为空）")

        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)

        tool_calls: list[ToolCall] = []
        for index, raw_call in enumerate(getattr(message, "tool_calls", None) or []):
            function = getattr(raw_call, "function", None)
            name = getattr(function, "name", "") or ""
            raw_arguments = getattr(function, "arguments", "") or ""
            arguments, parsed_ok = self._loads_arguments(raw_arguments)
            if not parsed_ok:
                # 参数不是合法 JSON 对象：置空 dict，并把原文留在 content 里供排查
                content = f"{content}\n{raw_arguments}".strip() if content else raw_arguments
            tool_calls.append(
                ToolCall(
                    id=getattr(raw_call, "id", "") or f"call_{index}",
                    name=name,
                    arguments=arguments,
                )
            )

        usage_obj = getattr(completion, "usage", None)
        usage: dict[str, int] = {}
        if usage_obj is not None:
            usage = {
                "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage_obj, "total_tokens", 0) or 0),
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=getattr(choice, "finish_reason", "") or "",
            usage=usage,
        )

    @staticmethod
    def _loads_arguments(raw: str) -> tuple[dict[str, Any], bool]:
        """解析工具实参；成功返回 (dict, True)，非法 JSON/非对象返回 ({}, False)。"""
        if not raw.strip():
            return {}, True
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}, False
        if isinstance(parsed, dict):
            return parsed, True
        return {}, False

    @staticmethod
    def _parse_json(content: str) -> Any:
        """解析 JSON 字符串；失败返回哨兵 _JSON_MISS。"""
        if not content or not content.strip():
            return _JSON_MISS
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return _JSON_MISS

    def _accumulate_usage(self, usage: dict[str, int]) -> None:
        """把本次调用的 token 用量累加到内部计数器。"""
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self._usage_totals[key] += int(usage.get(key, 0) or 0)

    def _describe_error(self, exc: BaseException, reason: str) -> str:
        """生成可写日志/可抛出的错误描述，自动脱敏 API Key 并截断长度。"""
        status = getattr(exc, "status_code", None)
        message = self._sanitize(str(exc))
        if status is not None:
            detail = f"{reason}：status={status} {message}"
        else:
            detail = f"{reason}：{type(exc).__name__} {message}"
        return detail[:500]

    def _sanitize(self, text: str) -> str:
        """把文本中可能出现的 API Key 替换为脱敏形式。"""
        key = self._settings.llm_api_key.strip()
        if key and key in text:
            text = text.replace(key, self._mask_key(key))
        return text

    @staticmethod
    def _mask_key(key: str) -> str:
        """只保留 Key 前 4 位，其余以 *** 代替。"""
        key = key.strip()
        if len(key) <= 4:
            return "***"
        return f"{key[:4]}***"
