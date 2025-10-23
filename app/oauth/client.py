from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config import OAUTH_SCOPE, TOKEN_URL, logger
from app.models import AccountCredentials


async def fetch_access_token(credentials: AccountCredentials) -> str:
    payload = {
        "client_id": credentials.client_id,
        "grant_type": "refresh_token",
        "refresh_token": credentials.refresh_token,
        "scope": OAUTH_SCOPE,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TOKEN_URL, data=payload)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("No access token in response for %s", credentials.email)
                raise HTTPException(status_code=401, detail="Failed to obtain access token from response")
            logger.info("Successfully obtained access token for %s", credentials.email)
            return access_token
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP %s error getting access token for %s: %s", exc.response.status_code, credentials.email, exc)
        if exc.response.status_code == 400:
            raise HTTPException(status_code=401, detail="Invalid refresh token or client credentials")
        raise HTTPException(status_code=401, detail="Authentication failed")
    except httpx.RequestError as exc:
        logger.error("Request error getting access token for %s: %s", credentials.email, exc)
        raise HTTPException(status_code=500, detail="Network error during token acquisition")
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error getting access token for %s: %s", credentials.email, exc)
        raise HTTPException(status_code=500, detail="Token acquisition failed")
