from __future__ import annotations

import email

from fastapi import HTTPException

from app.config import logger
from app.infrastructure.imap import imap_pool
from app.models import AccountCredentials, EmailDetailsResponse

from .utils import decode_header_value, extract_email_content, format_date


def fetch_email_detail(
    credentials: AccountCredentials,
    folder_name: str,
    msg_id: str,
    message_id: str,
    access_token: str,
    uid: str | None = None,
) -> tuple[EmailDetailsResponse, str | None]:
    imap_client = None
    try:
        imap_client = imap_pool.get_connection(credentials.email, access_token)
        imap_client.select(folder_name)
        if uid:
            status, msg_data = imap_client.uid("FETCH", uid, "(RFC822)")
        else:
            status, msg_data = imap_client.fetch(msg_id, "(RFC822)")
        if status != "OK" or not msg_data:
            raise HTTPException(status_code=404, detail="Email not found")

        raw_part = next((entry for entry in msg_data if isinstance(entry, tuple) and isinstance(entry[1], (bytes, bytearray))), None)
        if not raw_part:
            raise HTTPException(status_code=404, detail="Email not found")

        raw_email = raw_part[1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_header_value(msg.get("Subject", "(No Subject)"))
        from_email = decode_header_value(msg.get("From", "(Unknown Sender)"))
        to_email = decode_header_value(msg.get("To", "(Unknown Recipient)"))
        date_str = msg.get("Date", "")
        formatted_date = format_date(date_str)
        body_plain, body_html = extract_email_content(msg)

        resolved_uid = uid

        if not resolved_uid:
            uid_status, uid_data = imap_client.fetch(msg_id, "(UID)")
            if uid_status == "OK" and uid_data:
                header = uid_data[0][0]
                if isinstance(header, bytes):
                    header = header.decode(errors="ignore")
                if isinstance(header, str):
                    parts = header.split()
                    if "UID" in parts:
                        try:
                            uid_index = parts.index("UID")
                            resolved_uid = parts[uid_index + 1].strip(")")
                        except (ValueError, IndexError):  # noqa: PERF203
                            resolved_uid = None

        response = EmailDetailsResponse(
            message_id=message_id,
            subject=subject,
            from_email=from_email,
            to_email=to_email,
            date=formatted_date,
            body_plain=body_plain or None,
            body_html=body_html or None,
            uid=resolved_uid,
        )
        return response, resolved_uid
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


__all__ = ["fetch_email_detail"]
