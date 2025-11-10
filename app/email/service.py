from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.accounts import account_service
from app.config import logger
from app.models import AccountCredentials, EmailDetailsResponse, EmailListResponse
from app.oauth import fetch_access_token
from app.email.cache_store import (
    CachedEmailDetail,
    email_detail_cache_repository,
    email_list_cache_repository,
)

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
                account_service.record_token_failure(
                    credentials.email,
                    status_code=exc.status_code,
                    error_message=exc.detail,
                    operation="email_list_token_request"
                )
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
            email_list_cache_repository.save(
                credentials.email,
                folder,
                page,
                page_size,
                result.emails,
                result.total_emails,
            )
            for item in result.emails:
                if item.uid:
                    email_detail_cache_repository.register_stub(
                        credentials.email,
                        item.message_id,
                        item.folder,
                        item.uid,
                    )
            email_cache.set(cache_key, result)
            return result
        try:
            return await asyncio.to_thread(_sync_list)
        except HTTPException as exc:
            if exc.status_code >= 500:
                cached_db = await self._load_cached_list(credentials.email, folder, page, page_size)
                if cached_db:
                    email_cache.set(cache_key, cached_db)
                    return cached_db
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error listing emails for %s: %s", credentials.email, exc)
            cached_db = await self._load_cached_list(credentials.email, folder, page, page_size)
            if cached_db:
                email_cache.set(cache_key, cached_db)
                return cached_db
            raise HTTPException(status_code=500, detail="Failed to retrieve emails") from exc

    async def get_email_details(self, credentials: AccountCredentials, message_id: str) -> EmailDetailsResponse:
        try:
            folder_name, msg_id = message_id.split("-", 1)
        except ValueError as exc:  # noqa: B904
            raise HTTPException(status_code=400, detail="Invalid message_id format") from exc

        cached_detail = await asyncio.to_thread(
            email_detail_cache_repository.load,
            credentials.email,
            message_id,
        ) if email_detail_cache_repository.is_enabled else None

        detail_stub: CachedEmailDetail | None = cached_detail
        if cached_detail and cached_detail.response:
            cached_detail.response.from_cache = False
            return cached_detail.response

        effective_folder = detail_stub.folder if detail_stub and detail_stub.folder else folder_name
        uid_hint = detail_stub.uid if detail_stub else None

        try:
            access_token = await fetch_access_token(credentials)
        except HTTPException as exc:
            if exc.status_code in {401}:
                account_service.record_token_failure(
                    credentials.email,
                    status_code=exc.status_code,
                    error_message=exc.detail,
                    operation="email_detail_token_request"
                )
            raise

        account_service.record_token_success(credentials.email)

        def _sync_detail() -> tuple[EmailDetailsResponse, str | None]:
            return fetch_email_detail(
                credentials=credentials,
                folder_name=effective_folder,
                msg_id=msg_id,
                message_id=message_id,
                access_token=access_token,
                uid=uid_hint,
            )
        try:
            detail_response, resolved_uid = await asyncio.to_thread(_sync_detail)
            email_detail_cache_repository.save_detail(
                credentials.email,
                message_id,
                effective_folder,
                resolved_uid,
                detail_response,
            )
            return detail_response
        except HTTPException as exc:
            if exc.status_code >= 500:
                fallback = await self._load_cached_detail(credentials.email, message_id, effective_folder, uid_hint)
                if fallback:
                    return fallback
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error getting email details for %s: %s", credentials.email, exc)
            fallback = await self._load_cached_detail(credentials.email, message_id, effective_folder, uid_hint)
            if fallback:
                return fallback
            raise HTTPException(status_code=500, detail="Failed to retrieve email details") from exc

    async def _load_cached_list(
        self,
        email_id: str,
        folder: str,
        page: int,
        page_size: int,
    ) -> EmailListResponse | None:
        if not email_list_cache_repository.is_enabled:
            return None
        return await asyncio.to_thread(
            email_list_cache_repository.load,
            email_id,
            folder,
            page,
            page_size,
        )

    async def _load_cached_detail(
        self,
        email_id: str,
        message_id: str,
        folder: str,
        uid_hint: str | None,
    ) -> EmailDetailsResponse | None:
        if not email_detail_cache_repository.is_enabled:
            return None

        detail_record = await asyncio.to_thread(
            email_detail_cache_repository.load,
            email_id,
            message_id,
        )
        if detail_record and detail_record.response:
            return detail_record.response

        uid_candidate = uid_hint or (detail_record.uid if detail_record else None)
        if uid_candidate and folder:
            fallback = await asyncio.to_thread(
                email_detail_cache_repository.load_by_uid,
                email_id,
                folder,
                uid_candidate,
            )
            if fallback and fallback.response:
                return fallback.response
        return None

    def clear_cache(self, email_id: str | None = None) -> int:
        prefix = f"{email_id}:" if email_id else None
        return email_cache.clear(prefix)


email_service = EmailService()

__all__ = ["EmailService", "email_service"]
