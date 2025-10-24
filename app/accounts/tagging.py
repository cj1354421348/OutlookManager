from __future__ import annotations

from app.models import AccountCredentials, AccountResponse, UpdateTagsRequest

from .repository import AccountRepository


def update_account_tags(
    repository: AccountRepository,
    credentials: AccountCredentials,
    email_id: str,
    request: UpdateTagsRequest,
) -> AccountResponse:
    updated = {
        "refresh_token": credentials.refresh_token,
        "client_id": credentials.client_id,
        "tags": request.tags,
    }
    repository.save_account(email_id, updated)
    return AccountResponse(email_id=email_id, message="Account tags updated successfully.")


__all__ = ["update_account_tags"]
