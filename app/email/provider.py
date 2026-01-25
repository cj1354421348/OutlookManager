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
from app.email.details import fetch_email_detail

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
            
            target_folders = ["INBOX"] if folder == "inbox" else ["Junk"] if folder == "junk" else ["INBOX", "Junk"]
            
            # Step 1: Get counts for all folders to calculate total and plan pagination
            folder_counts: List[tuple[str, int]] = []
            total_emails = 0
            
            for folder_name in target_folders:
                try:
                    # SELECT command returns message count in response
                    status, valid_data = imap_client.select(f'"{folder_name}"', readonly=True)
                    
                    if status == "OK" and valid_data:
                         count = int(valid_data[0])
                         folder_counts.append((folder_name, count))
                         total_emails += count
                    else:
                         folder_counts.append((folder_name, 0))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to access folder %s: %s", folder_name, exc)
                    folder_counts.append((folder_name, 0))

            # Step 2: Calculate global pagination range
            email_items: List[EmailItem] = []
            
            # Global offset calculation
            emails_to_skip = (page - 1) * page_size
            emails_needed = page_size
            
            uid_pattern = re.compile(r"(\d+)\s+\(UID\s+(\d+)")

            for folder_name, count in folder_counts:
                if emails_needed <= 0:
                    break
                    
                if count <= emails_to_skip:
                    # Entire folder is before the requested page
                    emails_to_skip -= count
                    continue
                
                # We need emails from this folder
                # Available in this folder: [count, count-1, ... 1] (Newest is 'count')
                
                # Number of emails to take from this folder
                available_after_skip = count - emails_to_skip
                take_count = min(emails_needed, available_after_skip)
                
                # Sequence range calculation
                # high = count - emails_to_skip
                # low = high - take_count + 1
                
                high_seq = count - emails_to_skip
                low_seq = high_seq - take_count + 1
                
                # Consume skip for next folder (should be 0 now)
                emails_to_skip = 0
                emails_needed -= take_count
                
                if low_seq < 1: low_seq = 1 # Safety clamp
                
                sequence = f"{low_seq}:{high_seq}"
                
                try:
                    # Ensure we are selected on the right folder
                    imap_client.select(f'"{folder_name}"', readonly=True)
                    
                    uid_lookup: Dict[bytes, str] = {}
                    
                    # Fetch UIDs
                    status, uid_data = imap_client.fetch(sequence, "(UID)")
                    
                    if status == "OK" and uid_data:
                         for entry in uid_data:
                            header_text = None
                            if isinstance(entry, tuple):
                                header_text = entry[0]
                            elif isinstance(entry, (bytes, bytearray)):
                                header_text = entry
                            
                            if header_text:
                                if isinstance(header_text, (bytes, bytearray)):
                                    header_text = header_text.decode(errors="ignore")
                                match = uid_pattern.search(header_text or "")
                                if match:
                                    # Group 1 is seq (e.g. 123), Group 2 is UID
                                    seq_num = match.group(1).encode()
                                    uid_lookup[seq_num] = match.group(2)

                    # Fetch Headers
                    status, msg_data = imap_client.fetch(
                        sequence,
                        "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM MESSAGE-ID)])",
                    )
                    
                    if status == "OK":
                        parsed_messages = parse_headers(msg_data)
                        items = build_email_items(folder_name, parsed_messages, uid_lookup)
                        items.sort(key=lambda x: x.date or "", reverse=True)
                        email_items.extend(items)
                        
                except Exception as exc:  # noqa: BLE001
                     logger.warning("Failed to fetch sequence %s from %s: %s", sequence, folder_name, exc)

            # Re-sort combined result just in case (e.g. between inbox and junk if we mixed)
            # Actually our logic assumes Folder 1 > Folder 2.
            # But sorting by date is safer.
            email_items.sort(key=lambda item: item.date or "", reverse=True)

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
        return fetch_email_detail(
            credentials=credentials,
            folder_name=folder_name,
            msg_id=msg_id,
            message_id=message_id,
            access_token=access_token,
            uid=uid,
            host=self.host,
        )


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
