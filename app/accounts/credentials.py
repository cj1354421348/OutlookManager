from __future__ import annotations

from fastapi import HTTPException

from app.config import logger
from app.models import AccountCredentials

from .repository import AccountRepository


def get_account_credentials(
    repository: AccountRepository,
    email_id: str,
    *,
    accounts: dict[str, dict[str, object]] | None = None,
) -> AccountCredentials:
    data_source = accounts if accounts is not None else repository.read_all()
    if email_id not in data_source:
        logger.warning("Account %s not found in accounts file", email_id)
        raise HTTPException(status_code=404, detail=f"Account {email_id} not found")

    data = data_source[email_id]
    refresh_token = data.get("refresh_token")
    client_id = data.get("client_id")
    tags = data.get("tags", [])

    if not refresh_token or not client_id:
        logger.error("Account %s missing required fields", email_id)
        raise HTTPException(status_code=500, detail="Account configuration incomplete")

    return AccountCredentials(
        email=email_id,
        refresh_token=refresh_token,
        client_id=client_id,
        tags=tags,
    )


__all__ = ["get_account_credentials"]
