from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config import OAUTH_SCOPE, GRAPH_SCOPE, IMAP_SCOPE, TOKEN_URL, logger
from app.models import AccountCredentials
from app.core.traffic_logger import traffic_logger
import time


async def fetch_access_token(credentials: AccountCredentials, protocol: str | None = None) -> str:
    # Determine scope based on protocol
    # If protocol is explicitly Graph, use Graph Scope
    # If protocol is IMAP or None (Legacy/Default), use IMAP Scope
    # Note: 'auto' should be handled by caller orchestrating the discovery with specific protocols
    scope = IMAP_SCOPE
    if protocol == "graph_api":
        scope = GRAPH_SCOPE
    
    payload = {
        "client_id": credentials.client_id,
        "grant_type": "refresh_token",
        "refresh_token": credentials.refresh_token,
        "scope": scope,
    }

    start_time = time.monotonic()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TOKEN_URL, data=payload)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("No access token in response for %s", credentials.email)
                raise HTTPException(status_code=400, detail="Failed to obtain access token from response")
            
            # Log successful request
            duration = (time.monotonic() - start_time) * 1000
            traffic_logger.log(
                protocol="HTTP",
                account=credentials.email,
                action="POST /token",
                status="OK",
                duration_ms=duration,
                details="Refreshed access token successfully"
            )
            
            logger.info("Successfully obtained access token for %s", credentials.email)
            return access_token
    except httpx.HTTPStatusError as exc:
        duration = (time.monotonic() - start_time) * 1000
        error_msg = f"HTTP {exc.response.status_code} error getting access token"
        logger.error("%s for %s: %s", error_msg, credentials.email, exc)
        
        # Log failed request
        traffic_logger.log(
            protocol="HTTP",
            account=credentials.email,
            action="POST /token",
            status=f"HTTP {exc.response.status_code}",
            duration_ms=duration,
            details=str(exc)
        )
        
        if exc.response.status_code == 400:
            # If requesting Graph scope with an old token that only has IMAP consent, we get 400.
            # This is expected during Auto-Discovery probing.
            # Caller should handle the 400/401.
            raise HTTPException(status_code=400, detail="账户授权已过期或权限不足: Invalid refresh token or scope mismatch")
        raise HTTPException(status_code=400, detail="Authentication failed")
    except httpx.RequestError as exc:
        duration = (time.monotonic() - start_time) * 1000
        error_msg = "Request error getting access token"
        logger.error("%s for %s: %s", error_msg, credentials.email, exc)
        
        # Log network error
        traffic_logger.log(
            protocol="HTTP",
            account=credentials.email,
            action="POST /token",
            status="NETWORK_ERROR",
            duration_ms=duration,
            details=str(exc)
        )
        
        raise HTTPException(status_code=500, detail="Network error during token acquisition")
    except Exception as exc:  # noqa: BLE001
        duration = (time.monotonic() - start_time) * 1000
        error_msg = "Unexpected error getting access token"
        logger.error("%s for %s: %s", error_msg, credentials.email, exc)
        
        # Log unexpected error
        traffic_logger.log(
            protocol="HTTP",
            account=credentials.email,
            action="POST /token",
            status="ERROR",
            duration_ms=duration,
            details=str(exc)
        )
        
        raise HTTPException(status_code=500, detail="Token acquisition failed")
