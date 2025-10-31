from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.accounts import account_service
from app.models import AccountCredentials, EmailDetailsResponse, EmailListResponse
from app.oauth import fetch_access_token

from .cache import email_cache
from .details import fetch_email_detail
from .listing import fetch_email_list


class EmailService:
    @staticmethod
    def cache_key(email_id: str, folder: str, page: int, page_size: int) -> str:
        return f"{email_id}:{folder}:{page}:{page_size}"

    async def list_emails(
        self,
        credentials: AccountCredentials,
        folder: str,
        page: int,
        page_size: int,
        force_refresh: bool = False,
    ) -> EmailListResponse:
        cache_key = self.cache_key(credentials.email, folder, page, page_size)
        cached = email_cache.get(cache_key, force_refresh)
        if cached:
            return cached

        try:
            access_token = await fetch_access_token(credentials)
        except HTTPException as exc:
            if exc.status_code in {401}:
                account_service.record_token_failure(credentials.email, status_code=exc.status_code)
            raise

        account_service.record_token_success(credentials.email)

        def _sync_list() -> EmailListResponse:
            result = fetch_email_list(
                credentials=credentials,
                folder=folder,
                page=page,
                page_size=page_size,
                access_token=access_token,
            )
            email_cache.set(cache_key, result)
            return result

        return await asyncio.to_thread(_sync_list)

    async def get_email_details(self, credentials: AccountCredentials, message_id: str) -> EmailDetailsResponse:
        try:
            folder_name, msg_id = message_id.split("-", 1)
        except ValueError as exc:  # noqa: B904
            raise HTTPException(status_code=400, detail="Invalid message_id format") from exc

        try:
            access_token = await fetch_access_token(credentials)
        except HTTPException as exc:
            if exc.status_code in {401}:
                account_service.record_token_failure(credentials.email, status_code=exc.status_code)
            raise

        account_service.record_token_success(credentials.email)

        def _sync_detail() -> EmailDetailsResponse:
            return fetch_email_detail(
                credentials=credentials,
                folder_name=folder_name,
                msg_id=msg_id,
                message_id=message_id,
                access_token=access_token,
            )

        return await asyncio.to_thread(_sync_detail)

    def clear_cache(self, email_id: str | None = None) -> int:
        prefix = f"{email_id}:" if email_id else None
        return email_cache.clear(prefix)


email_service = EmailService()

__all__ = ["EmailService", "email_service"]
