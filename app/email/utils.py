from __future__ import annotations

import email
import re
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime

from app.config import logger


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


def extract_email_content(msg: email.message.EmailMessage) -> tuple[str, str]:
    body_plain = ""
    body_html = ""

    try:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition.lower():
                    continue
                try:
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    decoded_content = payload.decode(charset, errors="replace")
                    if content_type == "text/plain" and not body_plain:
                        body_plain = decoded_content
                    elif content_type == "text/html" and not body_html:
                        body_html = decoded_content
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to decode email part (%s): %s", content_type, exc)
        else:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                content = payload.decode(charset, errors="replace")
                content_type = msg.get_content_type()
                if content_type == "text/plain":
                    body_plain = content
                elif content_type == "text/html":
                    body_html = content
                else:
                    body_plain = content
    except Exception as exc:  # noqa: BLE001
        logger.error("Error extracting email content: %s", exc)

    return body_plain.strip(), body_html.strip()


def extract_sender_initial(from_email: str) -> str:
    match = re.search(r"([a-zA-Z])", from_email)
    return match.group(1).upper() if match else "?"


def format_date(date_str: str) -> str:
    try:
        if date_str:
            return parsedate_to_datetime(date_str).isoformat()
    except Exception:  # noqa: BLE001
        pass
    return datetime.now().isoformat()


__all__ = [
    "decode_header_value",
    "extract_email_content",
    "extract_sender_initial",
    "format_date",
]
