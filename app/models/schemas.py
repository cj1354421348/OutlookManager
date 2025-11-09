from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class AccountCredentials(BaseModel):
    email: EmailStr
    refresh_token: str
    client_id: str
    tags: Optional[List[str]] = Field(default=[])

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@outlook.com",
                "refresh_token": "0.AXoA...",
                "client_id": "your-client-id",
                "tags": ["工作", "个人"],
            }
        }


class EmailItem(BaseModel):
    message_id: str
    folder: str
    subject: str
    from_email: str
    date: str
    is_read: bool = False
    has_attachments: bool = False
    sender_initial: str = "?"
    uid: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "INBOX-123",
                "folder": "INBOX",
                "subject": "Welcome to Augment Code",
                "from_email": "noreply@augmentcode.com",
                "date": "2024-01-01T12:00:00",
                "is_read": False,
                "has_attachments": False,
                "sender_initial": "A",
            }
        }


class EmailListResponse(BaseModel):
    email_id: str
    folder_view: str
    page: int
    page_size: int
    total_emails: int
    emails: List[EmailItem]
    from_cache: bool = False


class DualViewEmailResponse(BaseModel):
    email_id: str
    inbox_emails: List[EmailItem]
    junk_emails: List[EmailItem]
    inbox_total: int
    junk_total: int


class EmailDetailsResponse(BaseModel):
    message_id: str
    subject: str
    from_email: str
    to_email: str
    date: str
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    uid: Optional[str] = None
    from_cache: bool = False


class AccountResponse(BaseModel):
    email_id: str
    message: str


class AccountInfo(BaseModel):
    email_id: str
    client_id: str
    status: str = "active"
    tags: List[str] = []
    note: Optional[str] = None


class AccountListResponse(BaseModel):
    total_accounts: int
    page: int
    page_size: int
    total_pages: int
    accounts: List[AccountInfo]


class UpdateTagsRequest(BaseModel):
    tags: List[str]


class UpdateNoteRequest(BaseModel):
    note: Optional[str] = None


class SyncResult(BaseModel):
    message: str
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    marked_deleted: int = 0


class LoginRequest(BaseModel):
    username: str
    password: str


class ApiKeyRequest(BaseModel):
    api_key: Optional[str] = None


class TokenHealthSettings(BaseModel):
    enabled: bool = True
