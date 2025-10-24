from __future__ import annotations

from math import ceil
from typing import Iterable, List, Optional

from app.models import AccountInfo, AccountListResponse


def build_account_list_response(
    accounts: Iterable[AccountInfo],
    page: int,
    page_size: int,
) -> AccountListResponse:
    accounts_list = list(accounts)
    total_accounts = len(accounts_list)
    total_pages = ceil(total_accounts / page_size) if total_accounts else 0
    start = (page - 1) * page_size
    end = start + page_size
    paginated = accounts_list[start:end]

    return AccountListResponse(
        total_accounts=total_accounts,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        accounts=paginated,
    )


def apply_account_filters(
    accounts: Iterable[AccountInfo],
    email_search: Optional[str],
    tag_search: Optional[str],
) -> List[AccountInfo]:
    result = list(accounts)
    if email_search:
        term = email_search.lower()
        result = [acc for acc in result if term in acc.email_id.lower()]
    if tag_search:
        tag_term = tag_search.lower()
        result = [acc for acc in result if any(tag_term in tag.lower() for tag in acc.tags)]
    return result


__all__ = ["apply_account_filters", "build_account_list_response"]
