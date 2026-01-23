from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config import logger, IMAP_PORT, CONNECTION_TIMEOUT, SOCKET_TIMEOUT
from app.models import AccountCredentials
from app.infrastructure.imap import LoggedIMAP4_SSL
import socket

# Protocol constants
PROTOCOL_GRAPH = "graph_api"
PROTOCOL_IMAP_OFFICE365 = "imap_office365"
PROTOCOL_IMAP_LIVE = "imap_live"
PROTOCOL_AUTO = "auto"

HOST_OFFICE365 = "outlook.office365.com"
HOST_LIVE = "outlook.live.com"

from app.oauth import fetch_access_token

async def detect_protocol(credentials: AccountCredentials) -> str:
    """
    Probes available protocols in order of preference:
    1. Graph API
    2. IMAP (Outlook Office365)
    3. IMAP (Outlook Live)
    
    Returns the detected protocol string.
    Raises HTTPException if all fail.
    """
    logger.info("Starting protocol auto-discovery for %s", credentials.email)
    
    # 1. Probe Graph API
    try:
        # Fetch specific token for Graph
        graph_token = await fetch_access_token(credentials, protocol=PROTOCOL_GRAPH)
        if await _probe_graph_api(graph_token):
            logger.info("Auto-discovery: %s supports Graph API", credentials.email)
            return PROTOCOL_GRAPH
    except Exception as e:
        # Log carefully - 400 means re-auth needed
        logger.info("Graph API available check skipped (likely needs re-auth for permissions): %s", e)

    # 2. Probe Old IMAP
    # For IMAP, we use the standard (legacy) token
    try:
        imap_token = await fetch_access_token(credentials, protocol=PROTOCOL_IMAP_OFFICE365)
        if _probe_imap(credentials.email, imap_token, HOST_OFFICE365):
            logger.info("Auto-discovery: %s supports IMAP Office365", credentials.email)
            return PROTOCOL_IMAP_OFFICE365

        # 3. Probe New IMAP - reuse IMAP token
        if _probe_imap(credentials.email, imap_token, HOST_LIVE):
            logger.info("Auto-discovery: %s supports IMAP Live", credentials.email)
            return PROTOCOL_IMAP_LIVE
    except Exception as e:
         logger.debug("IMAP probe skipped due to token error: %s", e)
        
    logger.error("Auto-discovery failed for %s: No supported protocol found", credentials.email)
    raise HTTPException(status_code=500, detail="Failed to detect supported email protocol.")


async def _probe_graph_api(access_token: str) -> bool:
    # Use mailFolders to check connectivity. This requires Mail.Read, not User.Read.
    url = "https://graph.microsoft.com/v1.0/me/mailFolders"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return True
            logger.debug("Graph API probe failed with status %s", response.status_code)
    except Exception as exc:
        logger.debug("Graph API probe failed: %s", exc)
    
    return False


def _probe_imap(email: str, access_token: str, host: str) -> bool:
    try:
        socket.setdefaulttimeout(SOCKET_TIMEOUT)
        client = LoggedIMAP4_SSL(host, IMAP_PORT, email_account=email)
        client.sock.settimeout(CONNECTION_TIMEOUT)
        auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")
        client.authenticate("XOAUTH2", lambda _: auth_string)
        
        # CRITICAL: Verify mailbox access to avoid "Authenticated but not connected" errors
        # This error happens when connecting to the wrong endpoint (e.g. Office365 vs Live)
        client.select("INBOX")
        
        client.logout()
        return True
    except Exception as exc:
        logger.debug("IMAP probe to %s failed: %s", host, exc)
    return False
