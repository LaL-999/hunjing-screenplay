"""FastAPI 入口 — 浑晶 · 剧创态 后端。

启动:
    cd backend
    uvicorn app.main:app --reload --port 8002

健康检查:
    GET /health → {"status":"ok","service":"hunjing-screenplay","version":"0.1.0"}
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.db.connection import init_db
from app.routers import novels, scenes, story_bibles

# ============================================================
# Logging — 默认 INFO 级别,业务模块可继续 getLogger 用
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# App 创建
# ============================================================
app = FastAPI(
    title="浑晶 · 剧创态 API",
    description="小说自动转剧本 YAML 的多 Agent 流水线后端",
    version=__version__,
)

# CORS — 允许前端 dev server 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 健康检查
# ============================================================
@app.get("/health")
def health() -> dict:
    """探活 endpoint — 测试 / 监控 / 评委复现都用这个。"""
    return {
        "status": "ok",
        "service": "hunjing-screenplay",
        "version": __version__,
        "llm_model": settings.deepseek_model,
        "llm_configured": not settings.deepseek_api_key.startswith("sk-NOT-SET"),
    }


# ============================================================
# 业务路由
# ============================================================
app.include_router(novels.router)
app.include_router(story_bibles.router)
app.include_router(scenes.router)


@app.get("/")
def root() -> dict:
    """根路径 — 给好奇打开浏览器直接访问的用户一个引导。"""
    return {
        "message": "浑晶 · 剧创态 API",
        "version": __version__,
        "health": "/health",
        "docs": "/docs",
    }


# ============================================================
# 启动日志(让用户看到配置加载成功)
# ============================================================
@app.on_event("startup")
async def on_startup() -> None:
    # 启动时初始化 DB(IF NOT EXISTS,幂等可重跑)
    init_db()
    logger.info("浑晶 · 剧创态 启动完成 v%s", __version__)
    logger.info("  LLM:   %s @ %s", settings.deepseek_model, settings.deepseek_api_base)
    logger.info("  DB:    %s", settings.database_path)
    logger.info("  Upload: %s", settings.upload_dir)
    logger.info("  CORS:  %s", ", ".join(settings.cors_origins))

    # API key 检查 — 未配时大字号警告(不阻断启动)
    if settings.deepseek_api_key.startswith("sk-NOT-SET"):
        logger.warning("")
        logger.warning("  ⚠  DEEPSEEK_API_KEY 未配置")
        logger.warning("  ⚠  非 LLM 功能(摄入 / 校验 / CLI)可用")
        logger.warning("  ⚠  需要 LLM 的功能(故事圣经自动抽取等)会返 401 / 502")
        logger.warning("  ⚠  解决:编辑 backend/.env 填入 DEEPSEEK_API_KEY")
        logger.warning("")
