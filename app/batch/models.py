from __future__ import annotations

from typing import List, Optional


class AccountCredentials:
    def __init__(self, email: str, refresh_token: str, client_id: str, tags: Optional[List[str]] = None) -> None:
        self.email = email
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.tags = tags or []


class EmailItem:
    def __init__(
        self,
        message_id: str,
        folder: str,
        subject: str,
        from_email: str,
        date: str,
        is_read: bool = False,
        has_attachments: bool = False,
        sender_initial: str = "?",
    ) -> None:
        self.message_id = message_id
        self.folder = folder
        self.subject = subject
        self.from_email = from_email
        self.date = date
        self.is_read = is_read
        self.has_attachments = has_attachments
        self.sender_initial = sender_initial

    def to_dict(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "folder": self.folder,
            "subject": self.subject,
            "from_email": self.from_email,
            "date": self.date,
            "is_read": self.is_read,
            "has_attachments": self.has_attachments,
            "sender_initial": self.sender_initial,
        }


__all__ = ["AccountCredentials", "EmailItem"]
