from __future__ import annotations

import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ACCOUNTS_FILE = "accounts.json"
SECURITY_FILE = "security.json"

ACCOUNTS_DB_HOST = os.getenv("ACCOUNTS_DB_HOST")
ACCOUNTS_DB_PORT = int(os.getenv("ACCOUNTS_DB_PORT", "3306"))
ACCOUNTS_DB_USER = os.getenv("ACCOUNTS_DB_USER")
ACCOUNTS_DB_PASSWORD = os.getenv("ACCOUNTS_DB_PASSWORD")
ACCOUNTS_DB_NAME = os.getenv("ACCOUNTS_DB_NAME")
ACCOUNTS_DB_TABLE = os.getenv("ACCOUNTS_DB_TABLE", "account_backups")
ACCOUNTS_SYNC_CONFLICT = os.getenv("ACCOUNTS_SYNC_CONFLICT", "prefer_local").lower()

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("outlook_manager")
