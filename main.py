"""Outlook邮件管理系统 - FastAPI入口

FastAPI 应用初始化、生命周期管理及路由装载。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import MAX_CONNECTIONS, logger
from app.infrastructure.imap import imap_pool
from app.routes import routers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Outlook Email Management System...")
    logger.info("IMAP connection pool initialized with max_connections=%s", MAX_CONNECTIONS)
    try:
        yield
    finally:
        logger.info("Shutting down Outlook Email Management System...")
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

    HOST = "0.0.0.0"
    PORT = 8000

    logger.info("Starting Outlook Email Management System on %s:%s", HOST, PORT)
    logger.info("Access the web interface at: http://localhost:%s", PORT)
    logger.info("Access the API documentation at: http://localhost:%s/docs", PORT)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info", access_log=True)
