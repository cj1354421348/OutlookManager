from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.accounts import account_service
from app.models import AccountCredentials, AccountListResponse, AccountResponse, SyncResult, UpdateTagsRequest
from app.security import require_api_key

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountListResponse)
async def get_accounts(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量，范围1-100"),
    email_search: str | None = Query(None, description="邮箱账号模糊搜索"),
    tag_search: str | None = Query(None, description="标签模糊搜索"),
    _: None = Depends(require_api_key),
) -> AccountListResponse:
    return account_service.list_accounts(page, page_size, email_search, tag_search)


@router.post("", response_model=AccountResponse)
async def register_account(
    credentials: AccountCredentials,
    _: None = Depends(require_api_key),
) -> AccountResponse:
    return await account_service.register_account(credentials)


@router.put("/{email_id}/tags", response_model=AccountResponse)
async def update_account_tags(
    email_id: str,
    request: UpdateTagsRequest,
    _: None = Depends(require_api_key),
) -> AccountResponse:
    return account_service.update_tags(email_id, request)


@router.delete("/{email_id}", response_model=AccountResponse)
async def delete_account(
    email_id: str,
    _: None = Depends(require_api_key),
) -> AccountResponse:
    return account_service.delete_account(email_id)


@router.post("/sync/push", response_model=SyncResult)
async def sync_accounts_to_database(
    _: None = Depends(require_api_key),
) -> SyncResult:
    report = account_service.sync_local_to_remote()
    return SyncResult(**report.to_dict())


@router.post("/sync/pull", response_model=SyncResult)
async def sync_accounts_from_database(
    _: None = Depends(require_api_key),
) -> SyncResult:
    report = account_service.sync_remote_to_local()
    return SyncResult(**report.to_dict())
