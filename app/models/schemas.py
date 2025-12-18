from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class TokenFailureDetails(BaseModel):
    count: int = 0
    first_failure_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    last_status_code: Optional[int] = None
    last_error_message: Optional[str] = None


class AccountSchema(BaseModel):
    """
    对应 accounts.json 中的完整账户条目结构
    """
    refresh_token: str
    client_id: str
    password: Optional[str] = None
    
    tags: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    
    status: str = "active"
    status_updated_at: Optional[str] = None
    status_reason: Optional[str] = None
    
    token_failures: Optional[TokenFailureDetails] = None
    
    last_modified_at: Optional[str] = None
    updated_at: Optional[str] = None  # 兼容字段

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "M.C550...",
                "client_id": "9e5f94bc...",
                "tags": ["work"],
                "status": "expired",
                "last_modified_at": "2025-12-06T13:00:00+08:00"
            }
        }


class AccountCredentials(AccountSchema):
    """
    扩展 AccountSchema 以包含 email 字段，主要用于 API 请求
    """
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@outlook.com",
                "refresh_token": "0.AXoA...",
                "client_id": "your-client-id",
                "password": "password",
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
    # 可以在这里添加更多字段用于前端展示，如 token_failures


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
    interval_minutes: int = Field(default=1440, ge=60, le=10080)


class BatchImportRequest(BaseModel):
    text: str
    default_password: str = "password"
