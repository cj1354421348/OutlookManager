from __future__ import annotations

import asyncio
import email
import re
from typing import Dict, List, Tuple

from fastapi import HTTPException

from app.config import logger
from app.infrastructure.imap import imap_pool
from app.models import AccountCredentials, EmailDetailsResponse, EmailItem, EmailListResponse
from app.oauth import fetch_access_token

from .cache import email_cache
from .utils import decode_header_value, extract_email_content, extract_sender_initial, format_date


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

        access_token = await fetch_access_token(credentials)

        def _sync_list() -> EmailListResponse:
            imap_client = None
            try:
                imap_client = imap_pool.get_connection(credentials.email, access_token)
                meta: List[Dict[str, bytes]] = []

                target_folders = ["INBOX"] if folder == "inbox" else ["Junk"] if folder == "junk" else ["INBOX", "Junk"]

                for folder_name in target_folders:
                    try:
                        imap_client.select(f'"{folder_name}"', readonly=True)
                        status, messages = imap_client.search(None, "ALL")
                        if status != "OK" or not messages or not messages[0]:
                            continue
                        message_ids = messages[0].split()
                        message_ids.reverse()
                        for msg_id in message_ids:
                            meta.append({"folder": folder_name.encode(), "id": msg_id})
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Failed to access folder %s: %s", folder_name, exc)

                total_emails = len(meta)
                start = (page - 1) * page_size
                end = start + page_size
                paginated = meta[start:end]

                grouped: Dict[str, List[bytes]] = {}
                for item in paginated:
                    folder_name = item["folder"].decode()
                    grouped.setdefault(folder_name, []).append(item["id"])

                email_items: List[EmailItem] = []

                for folder_name, ids in grouped.items():
                    try:
                        imap_client.select(f'"{folder_name}"', readonly=True)
                        if not ids:
                            continue
                        sequence = b",".join(ids)
                        status, msg_data = imap_client.fetch(
                            sequence,
                            "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM MESSAGE-ID)])",
                        )
                        if status != "OK":
                            continue
                        parsed_messages = self._parse_headers(msg_data)
                        email_items.extend(self._build_email_items(folder_name, parsed_messages))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Failed to fetch bulk emails from %s: %s", folder_name, exc)

                email_items.sort(key=lambda item: item.date, reverse=True)

                result = EmailListResponse(
                    email_id=credentials.email,
                    folder_view=folder,
                    page=page,
                    page_size=page_size,
                    total_emails=total_emails,
                    emails=email_items,
                )
                email_cache.set(cache_key, result)
                return result
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Error listing emails: %s", exc)
                raise HTTPException(status_code=500, detail="Failed to retrieve emails")
            finally:
                if imap_client:
                    try:
                        imap_pool.return_connection(credentials.email, imap_client)
                    except Exception:  # noqa: BLE001
                        pass

        return await asyncio.to_thread(_sync_list)

    async def get_email_details(self, credentials: AccountCredentials, message_id: str) -> EmailDetailsResponse:
        try:
            folder_name, msg_id = message_id.split("-", 1)
        except ValueError as exc:  # noqa: B904
            raise HTTPException(status_code=400, detail="Invalid message_id format") from exc

        access_token = await fetch_access_token(credentials)

        def _sync_detail() -> EmailDetailsResponse:
            imap_client = None
            try:
                imap_client = imap_pool.get_connection(credentials.email, access_token)
                imap_client.select(folder_name)
                status, msg_data = imap_client.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data:
                    raise HTTPException(status_code=404, detail="Email not found")

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                subject = decode_header_value(msg.get("Subject", "(No Subject)"))
                from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
                to_email = decode_header_value(msg.get("To", "(Unknown Recipient)"))
                date_str = msg.get("Date", "")
                formatted_date = format_date(date_str)
                body_plain, body_html = extract_email_content(msg)

                return EmailDetailsResponse(
                    message_id=message_id,
                    subject=subject,
                    from_email=from_email,
                    to_email=to_email,
                    date=formatted_date,
                    body_plain=body_plain or None,
                    body_html=body_html or None,
                )
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Error getting email details: %s", exc)
                raise HTTPException(status_code=500, detail="Failed to retrieve email details")
            finally:
                if imap_client:
                    try:
                        imap_pool.return_connection(credentials.email, imap_client)
                    except Exception:  # noqa: BLE001
                        pass

        return await asyncio.to_thread(_sync_detail)

    @staticmethod
    def _parse_headers(msg_data: List[Tuple[bytes, bytes]]) -> Dict[bytes, bytes]:
        parsed: Dict[bytes, bytes] = {}
        for entry in msg_data:
            if not isinstance(entry, tuple) or len(entry) < 2:
                continue
            header = entry[0]
            content = entry[1]
            match = re.match(rb"(\d+)\s+\(", header)
            if not match:
                continue
            msg_id = match.group(1)
            parsed[msg_id] = content
        return parsed

    @staticmethod
    def _build_email_items(folder_name: str, messages: Dict[bytes, bytes]) -> List[EmailItem]:
        items: List[EmailItem] = []
        for msg_id, header_data in messages.items():
            msg = email.message_from_bytes(header_data)
            subject = decode_header_value(msg.get("Subject", "(No Subject)"))
            from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
            date_str = msg.get("Date", "")
            formatted_date = format_date(date_str)
            message_id = f"{folder_name}-{msg_id.decode()}"
            sender_initial = extract_sender_initial(from_email)
            items.append(
                EmailItem(
                    message_id=message_id,
                    folder=folder_name,
                    subject=subject,
                    from_email=from_email,
                    date=formatted_date,
                    is_read=False,
                    has_attachments=False,
                    sender_initial=sender_initial,
                )
            )
        return items

    def clear_cache(self, email_id: str | None = None) -> int:
        prefix = f"{email_id}:" if email_id else None
        return email_cache.clear(prefix)


email_service = EmailService()

__all__ = ["EmailService", "email_service"]
