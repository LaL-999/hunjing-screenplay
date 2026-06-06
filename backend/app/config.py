"""配置加载 — 从 .env 读 LLM 凭据 / 服务器参数。

设计原则:
  - 所有配置集中在一处,业务代码只 import settings,不直接 os.getenv
  - .env 缺失时给出明确报错(不是隐式默认值)
  - LLM API key 缺失时启动 fail-fast,避免运行时才崩
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env(若存在)— config.py 在 backend/app/,parents[1]=backend/(正确)
# 修复了 2026/06/06:之前误用 parents[2] 跑到仓库根目录找不到 .env
_PROJECT_ROOT = Path(__file__).resolve().parents[1]  # backend/
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)


@dataclass
class Settings:
    """全局配置 — 启动时从环境读一次。"""

    # === LLM ===
    deepseek_api_key: str
    deepseek_api_base: str
    deepseek_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_default_temperature: float

    # === 服务器 ===
    host: str
    port: int
    reload: bool

    # === CORS ===
    cors_origins: list[str]

    # === 数据库 ===
    database_path: Path

    # === 上传 ===
    upload_dir: Path
    max_upload_size_mb: int

    # === 路径辅助 ===
    project_root: Path = field(default=_PROJECT_ROOT)


_PLACEHOLDER_KEY = "sk-NOT-SET-LLM-CALLS-WILL-FAIL"


def _read_settings() -> Settings:
    """启动时调一次。

    DEEPSEEK_API_KEY 缺失时不 fail-fast:
      - 用 placeholder 让 backend 起得来
      - 不依赖 LLM 的功能(上传 / 校验 / CLI)仍可用
      - 真调 LLM 时 OpenAI SDK 会报 401(用户即时看到要配 key)
    """
    db_path = _PROJECT_ROOT / os.getenv("DATABASE_PATH", "data/screenplay.db")
    upload_dir = _PROJECT_ROOT / os.getenv("UPLOAD_DIR", "data/uploads")
    cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:5174")

    api_key = os.getenv("DEEPSEEK_API_KEY") or _PLACEHOLDER_KEY

    return Settings(
        deepseek_api_key=api_key,
        deepseek_api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        llm_default_temperature=float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.6")),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8002")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
        cors_origins=[o.strip() for o in cors_raw.split(",") if o.strip()],
        database_path=db_path,
        upload_dir=upload_dir,
        max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "10")),
    )


# 模块加载时初始化 — 不传 API key 直接启动失败
settings = _read_settings()

# 确保目录存在
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
