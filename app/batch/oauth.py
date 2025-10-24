from __future__ import annotations

import httpx

from .config import OAUTH_SCOPE, TOKEN_URL, logger
from .models import AccountCredentials


async def get_access_token(credentials: AccountCredentials) -> str:
    token_request_data = {
        "client_id": credentials.client_id,
        "grant_type": "refresh_token",
        "refresh_token": credentials.refresh_token,
        "scope": OAUTH_SCOPE,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, proxies=None) as client:
            response = await client.post(TOKEN_URL, data=token_request_data)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("No access token in response for %s", credentials.email)
                raise ValueError("Failed to obtain access token from response")
            logger.info("Successfully obtained access token for %s", credentials.email)
            return access_token
    except httpx.HTTPStatusError as exc:  # noqa: BLE001
        logger.error("HTTP %s error getting access token for %s: %s", exc.response.status_code, credentials.email, exc)
        raise
    except httpx.RequestError as exc:  # noqa: BLE001
        logger.error("Request error getting access token for %s: %s", credentials.email, exc)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error getting access token for %s: %s", credentials.email, exc)
        raise


__all__ = ["get_access_token"]
