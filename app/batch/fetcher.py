from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Dict, List

from .config import logger
from .imap_pool import IMAPConnectionPool
from .models import AccountCredentials
from .oauth import get_access_token
from app.accounts import account_service


def decode_header_value(header_value: str) -> str:
    if not header_value:
        return ""

    try:
        decoded_parts = decode_header(str(header_value))
        decoded_string = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    encoding = charset if charset else "utf-8"
                    decoded_string += part.decode(encoding, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    decoded_string += part.decode("utf-8", errors="replace")
            else:
                decoded_string += str(part)
        return decoded_string.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to decode header value '%s': %s", header_value, exc)
        return str(header_value) if header_value else ""


async def list_emails(imap_pool: IMAPConnectionPool, credentials: AccountCredentials) -> List[Dict[str, object]]:
    try:
        access_token = await get_access_token(credentials)
    except Exception as exc:
        # 记录令牌获取失败
        account_service.record_token_failure(
            credentials.email,
            error_message=str(exc),
            operation="batch_email_list_token_request"
        )
        raise
    email_items: List[Dict[str, object]] = []
    imap_client: imaplib.IMAP4_SSL | None = None

    try:
        imap_client = await imap_pool.get_connection(credentials.email, access_token)
        folders_to_check = ["INBOX", "Junk"]

        for folder_name in folders_to_check:
            try:
                imap_client.select(f'"{folder_name}"', readonly=True)
                status, messages = imap_client.search(None, "ALL")
                if status != "OK" or not messages or not messages[0]:
                    logger.warning("No messages found in %s for %s", folder_name, credentials.email)
                    continue

                message_ids = messages[0].split()
                message_ids.reverse()

                for i in range(0, len(message_ids), 100):
                    batch_ids = message_ids[i : i + 100]
                    msg_id_sequence = b",".join(batch_ids)
                    status, msg_data = imap_client.fetch(
                        msg_id_sequence,
                        "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM MESSAGE-ID)])",
                    )
                    if status != "OK":
                        logger.warning("Failed to fetch emails from %s for %s", folder_name, credentials.email)
                        continue

                    for j in range(0, len(msg_data), 2):
                        if j + 1 >= len(msg_data):
                            continue

                        header_data = msg_data[j][1]

                        match = re.match(rb"(\d+)\s+\(", msg_data[j][0])
                        if not match:
                            continue
                        fetched_msg_id = match.group(1)

                        msg = email.message_from_bytes(header_data)
                        subject = decode_header_value(msg.get("Subject", "(No Subject)"))
                        from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
                        date_str = msg.get("Date", "")

                        try:
                            date_obj = parsedate_to_datetime(date_str) if date_str else datetime.now()
                            formatted_date = date_obj.isoformat()
                        except Exception:  # noqa: BLE001
                            date_obj = datetime.now()
                            formatted_date = date_obj.isoformat()

                        message_id = f"{folder_name}-{fetched_msg_id.decode()}"
                        sender_initial = "?"
                        if from_email:
                            email_match = re.search(r"([a-zA-Z])", from_email)
                            if email_match:
                                sender_initial = email_match.group(1).upper()

                        is_read = b"\\Seen" in msg_data[j][0]

                        email_items.append(
                            {
                                "email_id": credentials.email,
                                "message_id": message_id,
                                "folder": folder_name,
                                "subject": subject,
                                "from_email": from_email,
                                "date": formatted_date,
                                "is_read": is_read,
                                "sender_initial": sender_initial,
                            }
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch emails from %s for %s: %s", folder_name, credentials.email, exc)
                continue

        email_items.sort(key=lambda item: item["date"], reverse=True)
        if imap_client:
            await imap_pool.return_connection(credentials.email, imap_client)
        logger.info("Retrieved %s emails for %s", len(email_items), credentials.email)
        return email_items
    except Exception as exc:  # noqa: BLE001
        logger.error("Error listing emails for %s: %s", credentials.email, exc)
        
        # 记录IMAP操作失败
        account_service.record_token_failure(
            credentials.email,
            error_message=f"IMAP操作失败: {str(exc)}",
            operation="batch_email_list_imap_operation"
        )
        
        try:
            if imap_client and getattr(imap_client, "state", "") != "LOGOUT":
                await imap_pool.return_connection(credentials.email, imap_client)
        except Exception:  # noqa: BLE001
            pass
        raise


__all__ = ["decode_header_value", "list_emails"]
