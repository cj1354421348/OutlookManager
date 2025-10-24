from __future__ import annotations

from app.models import AccountCredentials, AccountResponse, UpdateTagsRequest

from .repository import AccountRepository


def update_account_tags(
    repository: AccountRepository,
    credentials: AccountCredentials,
    email_id: str,
    request: UpdateTagsRequest,
) -> AccountResponse:
    accounts = repository.read_all()
    existing = dict(accounts.get(email_id, {}))

    existing.update(
        {
            "refresh_token": credentials.refresh_token,
            "client_id": credentials.client_id,
            "tags": request.tags,
        }
    )

    repository.save_account(email_id, existing)
    return AccountResponse(email_id=email_id, message="Account tags updated successfully.")


__all__ = ["update_account_tags"]
