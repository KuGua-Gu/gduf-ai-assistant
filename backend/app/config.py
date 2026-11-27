"""全局配置：所有可变参数通过环境变量注入（参考根目录 .env.example）。"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/
REPO_ROOT = BACKEND_DIR.parent  # 仓库根目录


class Settings(BaseSettings):
    """服务与 Agent 运行参数。"""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 大模型（OpenAI 兼容协议）
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"

    # 视觉模型（小票识别；DeepSeek 文本模型不支持图片，需单独配置多模态模型）
    vision_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    vision_api_key: str = ""
    vision_model: str = ""

    # 服务
    db_path: str = "data/app.db"
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    # OCR 上传
    ocr_upload_dir: str = "data/uploads"
    ocr_max_bytes: int = 10 * 1024 * 1024

    # Agent 行为
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    agent_max_tool_calls: int = 4
    agent_memory_window: int = 8

    @field_validator(
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "vision_base_url",
        "vision_api_key",
        "vision_model",
        mode="before",
    )
    @classmethod
    def _strip_llm_fields(cls, value: object) -> object:
        """去掉从 .env 复制时常见的首尾空格，避免污染请求头。"""
        return value.strip() if isinstance(value, str) else value

    @property
    def llm_configured(self) -> bool:
        """是否已配置可用的 API Key（占位值视为未配置）。"""
        key = self.llm_api_key.strip()
        return bool(key) and not key.startswith("sk-your")

    @property
    def resolved_db_path(self) -> Path:
        path = Path(self.db_path)
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def resolved_upload_dir(self) -> Path:
        """OCR 上传目录，相对路径基于仓库根目录解析。"""
        path = Path(self.ocr_upload_dir)
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def vision_configured(self) -> bool:
        """是否配置了可用的视觉模型（Key 与模型名都不为空）。"""
        key = self.vision_api_key.strip()
        return bool(key) and not key.startswith("sk-your") and bool(self.vision_model.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
