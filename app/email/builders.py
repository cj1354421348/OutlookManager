from __future__ import annotations

import email
import re
from typing import Dict, List, Tuple

from app.email.utils import decode_header_value, extract_sender_initial, format_date
from app.models import EmailItem

_HEADER_ID_PATTERN = re.compile(rb"(\d+)\s+\(")


def parse_headers(msg_data: List[Tuple[bytes, bytes]]) -> Dict[bytes, bytes]:
    parsed: Dict[bytes, bytes] = {}
    for entry in msg_data:
        if not isinstance(entry, tuple) or len(entry) < 2:
            continue
        header, content = entry[0], entry[1]
        match = _HEADER_ID_PATTERN.match(header)
        if not match:
            continue
        msg_id = match.group(1)
        parsed[msg_id] = content
    return parsed


def build_email_items(
    folder_name: str,
    messages: Dict[bytes, bytes],
    uid_lookup: Dict[bytes, str] | None = None,
) -> List[EmailItem]:
    items: List[EmailItem] = []
    uid_lookup = uid_lookup or {}
    for msg_id, header_data in messages.items():
        msg = email.message_from_bytes(header_data)
        subject = decode_header_value(msg.get("Subject", "(No Subject)"))
        from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
        date_str = msg.get("Date", "")
        formatted_date = format_date(date_str)
        message_id = f"{folder_name}-{msg_id.decode()}"
        sender_initial = extract_sender_initial(from_email)
        uid_value = uid_lookup.get(msg_id)
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
                uid=uid_value,
            )
        )
    return items


__all__ = ["build_email_items", "parse_headers"]
