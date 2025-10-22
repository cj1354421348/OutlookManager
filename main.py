"""
Outlook邮件管理系统 - FastAPI入口

FastAPI 应用初始化、生命周期管理及路由装载。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import MAX_CONNECTIONS, logger
from app.routes import routers
from app.services.imap_pool import imap_pool


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


if __name__ == "__main__":
    import uvicorn

    HOST = "0.0.0.0"
    PORT = 8000

    logger.info("Starting Outlook Email Management System on %s:%s", HOST, PORT)
    logger.info("Access the web interface at: http://localhost:%s", PORT)
    logger.info("Access the API documentation at: http://localhost:%s/docs", PORT)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info", access_log=True)
