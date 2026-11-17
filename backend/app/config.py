"""全局配置：所有可变参数通过环境变量注入（参考根目录 .env.example）。"""

from functools import lru_cache
from pathlib import Path

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
    vision_model: str = ""

    # 服务
    db_path: str = "data/app.db"
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    # Agent 行为
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    agent_max_tool_calls: int = 4
    agent_memory_window: int = 8

    @property
    def llm_configured(self) -> bool:
        """是否已配置可用的 API Key（占位值视为未配置）。"""
        key = self.llm_api_key.strip()
        return bool(key) and not key.startswith("sk-your")

    @property
    def resolved_db_path(self) -> Path:
        path = Path(self.db_path)
        return path if path.is_absolute() else REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
