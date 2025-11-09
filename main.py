"""Outlook邮件管理系统 - FastAPI入口

FastAPI 应用初始化、生命周期管理及路由装载。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.accounts.service import account_repository
from app.config import MAX_CONNECTIONS, logger
from app.core.token_health import TokenHealthScheduler, TokenHealthService
from app.infrastructure.imap import imap_pool
from app.routes import routers
from app.security import security_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Outlook Email Management System...")
    logger.info("IMAP connection pool initialized with max_connections=%s", MAX_CONNECTIONS)
    token_health_service = TokenHealthService(account_repository)
    token_health_scheduler = TokenHealthScheduler(
        token_health_service,
        security_service.is_token_health_enabled,
        security_service.get_token_health_interval,
    )
    app.state.token_health_scheduler = token_health_scheduler
    token_health_scheduler.start()
    try:
        yield
    finally:
        logger.info("Shutting down Outlook Email Management System...")
        logger.info("Stopping token health scheduler...")
        scheduler = getattr(app.state, "token_health_scheduler", None)
        if scheduler:
            await scheduler.stop()
        logger.info("Closing IMAP connection pool...")
        imap_pool.close_all_connections()
        logger.info("Application shutdown complete.")


app = FastAPI(
    title="Outlook邮件API服务",
    description="基于FastAPI和IMAP协议的高性能邮件管理系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in routers:
    app.include_router(router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def add_static_cache_headers(request, call_next):
    response = await call_next(request)
    try:
        if request.url.path.startswith("/static/"):
            # 轻量缓存：1小时，避免过度缓存导致更新不生效
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
    except Exception:
        pass
    return response


if __name__ == "__main__":
    import uvicorn
    import os

    # 从环境变量读取配置，如果未设置则使用默认值
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
    WORKERS = int(os.getenv("WORKERS", "1"))

    logger.info("Starting Outlook Email Management System on %s:%s", HOST, PORT)
    logger.info("Access the web interface at: http://localhost:%s", PORT)
    logger.info("Access the API documentation at: http://localhost:%s/docs", PORT)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info", access_log=True)
