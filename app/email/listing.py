from __future__ import annotations

import re
from typing import Dict, List

from fastapi import HTTPException

from app.config import logger
from app.infrastructure.imap import imap_pool
from app.models import AccountCredentials, EmailItem, EmailListResponse

from .builders import build_email_items, parse_headers


def fetch_email_list(
    credentials: AccountCredentials,
    folder: str,
    page: int,
    page_size: int,
    access_token: str,
) -> EmailListResponse:
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

        uid_pattern = re.compile(r"(\d+)\s+\(UID\s+(\d+)")

        for folder_name, ids in grouped.items():
            try:
                imap_client.select(f'"{folder_name}"', readonly=True)
                if not ids:
                    continue
                sequence = b",".join(ids)
                uid_lookup: Dict[bytes, str] = {}
                status, uid_data = imap_client.fetch(sequence, "(UID)")
                if status == "OK" and uid_data:
                    for entry in uid_data:
                        header_text = None
                        if isinstance(entry, tuple):
                            header_text = entry[0]
                        elif isinstance(entry, (bytes, bytearray)):
                            header_text = entry
                        if not header_text:
                            continue
                        if isinstance(header_text, (bytes, bytearray)):
                            header_text = header_text.decode(errors="ignore")
                        match = uid_pattern.search(header_text or "")
                        if match:
                            seq_num = match.group(1).encode()
                            uid_lookup[seq_num] = match.group(2)
                status, msg_data = imap_client.fetch(
                    sequence,
                    "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM MESSAGE-ID)])",
                )
                if status != "OK":
                    continue
                parsed_messages = parse_headers(msg_data)
                email_items.extend(build_email_items(folder_name, parsed_messages, uid_lookup))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch bulk emails from %s: %s", folder_name, exc)

        email_items.sort(key=lambda item: item.date, reverse=True)

        response = EmailListResponse(
            email_id=credentials.email,
            folder_view=folder,
            page=page,
            page_size=page_size,
            total_emails=total_emails,
            emails=email_items,
        )
        return response
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


__all__ = ["fetch_email_list"]
