from __future__ import annotations

import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ACCOUNTS_FILE = "accounts.json"
SECURITY_FILE = "security.json"

# 数据库配置 - 使用默认值，连接到外部PostgreSQL数据库
ACCOUNTS_DB_HOST = os.getenv("ACCOUNTS_DB_HOST", "localhost")
ACCOUNTS_DB_PORT = int(os.getenv("ACCOUNTS_DB_PORT", "5432"))
ACCOUNTS_DB_USER = os.getenv("ACCOUNTS_DB_USER", "outlook_user")
ACCOUNTS_DB_PASSWORD = os.getenv("ACCOUNTS_DB_PASSWORD", "secure_password")
ACCOUNTS_DB_NAME = os.getenv("ACCOUNTS_DB_NAME", "outlook_db")

# 完整的数据库连接URL（可选，如果提供则优先使用）
DATABASE_URL = os.getenv("DATABASE_URL", "")

ACCOUNTS_DB_TABLE = os.getenv("ACCOUNTS_DB_TABLE", "account_backups")
ACCOUNTS_SYNC_CONFLICT = os.getenv("ACCOUNTS_SYNC_CONFLICT", "prefer_local").lower()
EMAIL_LIST_CACHE_TABLE = os.getenv("EMAIL_LIST_CACHE_TABLE", "email_list_cache")
EMAIL_DETAIL_CACHE_TABLE = os.getenv("EMAIL_DETAIL_CACHE_TABLE", "email_detail_cache")

TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
OAUTH_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"

IMAP_SERVER = "outlook.live.com"
IMAP_PORT = 993
MAX_CONNECTIONS = 5
CONNECTION_TIMEOUT = 30
SOCKET_TIMEOUT = 15

CACHE_EXPIRE_TIME = 60

SESSION_COOKIE_NAME = "outlook_manager_session"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_SAMESITE = "lax"
APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin")
LOCK_THRESHOLD = 5
LOCK_DURATION_SECONDS = 3600

# 令牌失败阈值配置
TOKEN_FAILURE_THRESHOLD = int(os.getenv("TOKEN_FAILURE_THRESHOLD", "8"))
TOKEN_FAILURE_WINDOW_HOURS = int(os.getenv("TOKEN_FAILURE_WINDOW_HOURS", "12"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("outlook_manager")
