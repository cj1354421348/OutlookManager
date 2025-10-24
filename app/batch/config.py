from __future__ import annotations

import logging


ACCOUNTS_FILE = "accounts.json"
OUTPUT_DIR = "email_lists"
OUTPUT_FILE_FORMAT = "{email_id}_{date}.json"

TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
OAUTH_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"

IMAP_SERVER = "outlook.live.com"
IMAP_PORT = 993

MAX_CONNECTIONS = 5
CONNECTION_TIMEOUT = 30
SOCKET_TIMEOUT = 15


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("app.batch")


__all__ = [
    "ACCOUNTS_FILE",
    "CONNECTION_TIMEOUT",
    "IMAP_PORT",
    "IMAP_SERVER",
    "MAX_CONNECTIONS",
    "OAUTH_SCOPE",
    "OUTPUT_DIR",
    "OUTPUT_FILE_FORMAT",
    "SOCKET_TIMEOUT",
    "TOKEN_URL",
    "logger",
]
