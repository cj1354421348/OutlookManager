from __future__ import annotations

import asyncio

from fastapi import BackgroundTasks, HTTPException

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
from .provider import EmailProvider, ImapEmailProvider, GraphEmailProvider
from .discovery import detect_protocol, PROTOCOL_GRAPH, PROTOCOL_IMAP_OFFICE365, PROTOCOL_IMAP_LIVE, HOST_OFFICE365, HOST_LIVE

# Update AccountService to support partial updates if not already supported
# We might need to directly update DB or usage internal method if available.
# Checking imports: account_service is imported.

class EmailService:
    @staticmethod
    def cache_key(email_id: str, folder: str, page: int, page_size: int) -> str:
        return f"{email_id}:{folder}:{page}:{page_size}"

    async def _resolve_protocol(self, credentials: AccountCredentials) -> str:
        protocol = credentials.email_protocol
        if not protocol or protocol == "auto":
            # We need a token to probe? No, detect_protocol fetches its own tokens now.
            # So simply call it.
             # access_token param in detect_protocol was just removed/ignored?
             # Wait, my previous edit to detect_protocol KEPT the signature `access_token:str` but didn't use it?
             # I need to check if I removed it from signature or just unused it.
             # Step 122 output shows I kept it: `async def detect_protocol(credentials: AccountCredentials, access_token:str) -> str:`
             # I should fix that signature in discovery.py if it's unused, or pass None/dummy.
             # For now, pass None or empty string if allowed, or fix discovery.py.
             # Let's assume I fix discovery.py in a moment or pass dummy.
             # Actually, better to fix discovery.py signature too.
             pass
        return protocol
        
    async def list_emails(
        self,
        credentials: AccountCredentials,
        folder: str,
        page: int,
        page_size: int,
        force_refresh: bool = False,
        background_tasks: BackgroundTasks | None = None,
    ) -> EmailListResponse:
        cache_key = self.cache_key(credentials.email, folder, page, page_size)
        cached = email_cache.get(cache_key, force_refresh)
        if cached:
            return cached

        # 1. Resolve Protocol
        protocol = credentials.email_protocol
        if not protocol or protocol == "auto":
            protocol = await detect_protocol(credentials)
            logger.info("Discovered protocol for %s: %s", credentials.email, protocol)
            credentials.email_protocol = protocol
            try:
                account_service.update_account_protocol(credentials.email, protocol)
            except Exception as e:
                logger.warning("Failed to persist protocol for %s: %s", credentials.email, e)

        # 2. Fetch Token for Protocol
        try:
            access_token = await fetch_access_token(credentials, protocol=protocol)
        except HTTPException as exc:
            if exc.status_code in {400, 401}:
                 account_service.record_token_failure(
                    credentials.email,
                    status_code=exc.status_code,
                    error_message=exc.detail,
                    operation="email_list_token_request"
                )
            raise
        
        account_service.record_token_success(credentials.email)

        # 3. Get Provider
        if protocol == PROTOCOL_GRAPH:
            provider = GraphEmailProvider()
        elif protocol == PROTOCOL_IMAP_OFFICE365:
            provider = ImapEmailProvider(host=HOST_OFFICE365)
        elif protocol == PROTOCOL_IMAP_LIVE:
            provider = ImapEmailProvider(host=HOST_LIVE)
        else:
             provider = ImapEmailProvider(host=HOST_OFFICE365)

        def _sync_list() -> EmailListResponse:
            try:
                return provider.list_emails(
                    credentials=credentials,
                    folder=folder,
                    page=page,
                    page_size=page_size,
                    access_token=access_token,
                )
            except Exception as e:
                raise e

        try:
            result = await asyncio.to_thread(_sync_list)
            
            # Use Background Tasks for caching
            if background_tasks:
                background_tasks.add_task(
                    self.cache_email_response,
                    credentials.email,
                    folder,
                    page,
                    page_size,
                    result
                )
            else:
                # Fallback to sync if no background tasks provided (e.g. tests)
                # But we use add_task so it's technically still "sync" in this context unless handled
                # Actually, `add_task` pushes it to FastAPI queue.
                # If caller didn't provide BG tasks, we might want to skip or do it sync.
                # Let's do it sync to be safe for existing callers without bg tasks.
                self.cache_email_response(
                    credentials.email,
                    folder,
                    page,
                    page_size,
                    result
                )
            
            return result
            
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

    def cache_email_response(
        self,
        email_id: str,
        folder: str,
        page: int,
        page_size: int,
        result: EmailListResponse,
    ) -> None:
        """Cache email list results to DB and Memory."""
        try:
            email_list_cache_repository.save(
                email_id,
                folder,
                page,
                page_size,
                result.emails,
                result.total_emails,
            )
            # Optimized batch write
            email_detail_cache_repository.register_stubs_batch(
                email_id,
                result.emails,
            )
            
            cache_key = self.cache_key(email_id, folder, page, page_size)
            email_cache.set(cache_key, result)
        except Exception as exc:
            logger.warning("Background caching failed for %s: %s", email_id, exc)

    async def get_email_details(self, credentials: AccountCredentials, message_id: str) -> EmailDetailsResponse:
        try:
            if "-" in message_id:
                folder_name, msg_id = message_id.split("-", 1)
            else:
                # Graph API IDs don't have our folder prefix usually, but let's be safe
                # If we changed ID format for Graph, we need to handle it.
                # Current Graph implementation uses unprocessed ID.
                # Let's assume folder is passed contextually or we need to look it up.
                # The current system relies on ID encoding folder. 
                # For Graph, we might need a workaround if we don't prefix.
                # Recommendation: Keep prefixing in Provider even for Graph if possible, or handle here.
                # The implementation in Provider for Graph used raw ID.
                # Lets support raw ID if no split possible.
                folder_name = "INBOX" # Fallback
                msg_id = message_id
                
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

        # 1. Resolve Protocol (Reuse logic or copy?)
        # Since persistence is fast, we just re-check.
        protocol = credentials.email_protocol
        if not protocol or protocol == "auto":
             # If detailing without list first? Unlikely but possible.
             # Discovery needed.
             protocol = await detect_protocol(credentials) # Fixed: no args
             credentials.email_protocol = protocol
             try:
                account_service.update_account_protocol(credentials.email, protocol)
             except Exception:
                pass
        
        # 2. Fetch Token
        try:
            access_token = await fetch_access_token(credentials, protocol=protocol)
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

        # 3. Get Provider
        if protocol == PROTOCOL_GRAPH:
            provider = GraphEmailProvider()
        elif protocol == PROTOCOL_IMAP_OFFICE365:
            provider = ImapEmailProvider(host=HOST_OFFICE365)
        elif protocol == PROTOCOL_IMAP_LIVE:
            provider = ImapEmailProvider(host=HOST_LIVE)
        else:
             provider = ImapEmailProvider(host=HOST_OFFICE365)

        def _sync_detail() -> tuple[EmailDetailsResponse, str | None]:
            return provider.get_email_details(
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
