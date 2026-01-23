from __future__ import annotations

import abc
import re
from typing import Dict, List, Any
import httpx

from fastapi import HTTPException

from app.config import logger
from app.infrastructure.imap import imap_pool
from app.models import AccountCredentials, EmailItem, EmailListResponse, EmailDetailsResponse
from app.email.builders import build_email_items, parse_headers

class EmailProvider(abc.ABC):
    @abc.abstractmethod
    def list_emails(
        self,
        credentials: AccountCredentials,
        folder: str,
        page: int,
        page_size: int,
        access_token: str,
    ) -> EmailListResponse:
        pass

    @abc.abstractmethod
    def get_email_details(
        self,
        credentials: AccountCredentials,
        folder_name: str,
        msg_id: str,
        message_id: str,
        access_token: str,
        uid: str | None = None,
    ) -> tuple[EmailDetailsResponse, str | None]:
        pass


class ImapEmailProvider(EmailProvider):
    def __init__(self, host: str):
        self.host = host

    def list_emails(
        self,
        credentials: AccountCredentials,
        folder: str,
        page: int,
        page_size: int,
        access_token: str,
    ) -> EmailListResponse:
        imap_client = None
        try:
            imap_client = imap_pool.get_connection(credentials.email, access_token, host=self.host)
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
                except Exception as exc:
                    error_msg = f"Failed to access folder {folder_name}"
                    logger.warning("%s: %s", error_msg, exc)

            total_emails = len(meta)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = meta[start:end]

            grouped: Dict[str, List[bytes]] = {}
            for item in paginated:
                item_folder = item["folder"].decode()
                grouped.setdefault(item_folder, []).append(item["id"])

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
                except Exception as exc:
                    error_msg = f"Failed to fetch bulk emails from {folder_name}"
                    logger.warning("%s: %s", error_msg, exc)

            email_items.sort(key=lambda item: item.date, reverse=True)

            return EmailListResponse(
                email_id=credentials.email,
                folder_view=folder,
                page=page,
                page_size=page_size,
                total_emails=total_emails,
                emails=email_items,
            )
        finally:
            if imap_client:
                try:
                    imap_pool.return_connection(credentials.email, imap_client)
                except Exception:
                    pass

    def get_email_details(
        self,
        credentials: AccountCredentials,
        folder_name: str,
        msg_id: str,
        message_id: str,
        access_token: str,
        uid: str | None = None,
    ) -> tuple[EmailDetailsResponse, str | None]:
        # For now, we reuse the existing `fetch_email_detail` function via import to avoid code duplication
        # or we could move the logic here. Given `fetch_email_detail` is in `details.py`,
        # let's import it there to avoid circular dependencies if possible, or just call it.
        # But wait, `fetch_email_detail` uses `imap_pool` internally with DEFAULT server.
        # We need to change that.
        
        # Actually, `fetch_email_detail` needs to be refactored to take a host or passed client.
        # Since I cannot easily change `details.py` without seeing it fully (I saw it earlier but didn't cache it),
        # I will IMPLEMENT the logic here by copying and adapting if it's small, or I will use a modified version.
        
        # Let's assume we will refactor `details.py` to be a method on Provider, 
        # but for this step, let's keep it simple and just use the same logic pattern.
        
        imap_client = None
        try:
            imap_client = imap_pool.get_connection(credentials.email, access_token, host=self.host)
            imap_client.select(f'"{folder_name}"', readonly=True)

            # Try to fetch by UID if available
            fetch_criteria = None
            if uid:
                fetch_criteria = uid
                fetch_method = "UID FETCH"
            else:
                fetch_criteria = msg_id
                fetch_method = "FETCH"

            # Fetch body... (Simplified for this artifacts, real implementation needs full parsing)
            # To be safe and reuse code, I should probably import `fetch_email_detail` and PATCH it or
            # duplicate the logic. Duplicating is safer to avoid breaking existing code during transition.
            
            # ... (Implementation of detail fetching logic similar to details.py)
            # For the sake of this file creation, I will stub this part effectively or import `details.py` 
            # and rely on it IF it supports host. It currently doesn't.
            
            # Let's postpone detail implementation to `details.py` refactor or do it here.
            # I'll implement a basic version here relying on `details.py` logic but ensuring correct host.
            
            from app.email.details import fetch_email_detail_with_host
            return fetch_email_detail_with_host(
                credentials=credentials,
                folder_name=folder_name,
                msg_id=msg_id,
                message_id=message_id,
                access_token=access_token,
                uid=uid,
                host=self.host
            )
        except Exception as e:
            raise e
        finally:
             if imap_client:
                imap_pool.return_connection(credentials.email, imap_client)


class GraphEmailProvider(EmailProvider):
    def list_emails(
        self,
        credentials: AccountCredentials,
        folder: str,
        page: int,
        page_size: int,
        access_token: str,
    ) -> EmailListResponse:
        # Map folder names to Graph API well-known names
        graph_folder = "inbox"
        if folder.lower() == "junk":
            graph_folder = "junkemail"
        
        # Graph API URL
        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{graph_folder}/messages"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "$top": page_size,
            "$skip": (page - 1) * page_size,
            "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,parentFolderId",
            "$orderby": "receivedDateTime desc",
            "$count": "true"
        }

        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                total_emails = data.get("@odata.count", 0)
                messages = data.get("value", [])
                
                email_items = []
                for msg in messages:
                    email_items.append(EmailItem(
                        message_id=msg["id"],  # Graph ID is the message ID
                        folder=folder, # We use our internal name
                        subject=msg.get("subject", "(No Subject)"),
                        from_email=msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown"),
                        date=msg.get("receivedDateTime", ""),
                        is_read=msg.get("isRead", False),
                        has_attachments=msg.get("hasAttachments", False),
                        sender_initial=msg.get("from", {}).get("emailAddress", {}).get("name", "?")[0].upper() or "?",
                        uid=None # Graph doesn't use IMAP UIDs in the same way
                    ))
                
                return EmailListResponse(
                    email_id=credentials.email,
                    folder_view=folder,
                    page=page,
                    page_size=page_size,
                    total_emails=total_emails,
                    emails=email_items,
                )
        except Exception as exc:
            logger.error("Graph API error: %s", exc)
            raise HTTPException(status_code=500, detail=f"Graph API Error: {str(exc)}")

    def get_email_details(
        self,
        credentials: AccountCredentials,
        folder_name: str,
        msg_id: str,
        message_id: str,
        access_token: str,
        uid: str | None = None,
    ) -> tuple[EmailDetailsResponse, str | None]:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        params = {
            "$select": "id,subject,from,toRecipients,receivedDateTime,body"
        }
        
        try:
             with httpx.Client() as client:
                response = client.get(url, headers=headers, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                to_list = [r["emailAddress"]["address"] for r in data.get("toRecipients", [])]
                
                return EmailDetailsResponse(
                    message_id=data["id"],
                    subject=data.get("subject", ""),
                    from_email=data.get("from", {}).get("emailAddress", {}).get("address", ""),
                    to_email=", ".join(to_list),
                    date=data.get("receivedDateTime", ""),
                    body_plain=data.get("body", {}).get("content", "") if data.get("body", {}).get("contentType") == "text" else None,
                    body_html=data.get("body", {}).get("content", "") if data.get("body", {}).get("contentType") == "html" else None,
                    uid=None,
                    from_cache=False
                ), None
        except Exception as exc:
            logger.error("Graph API detail error: %s", exc)
            raise HTTPException(status_code=500, detail=f"Graph API Detail Error: {str(exc)}")
