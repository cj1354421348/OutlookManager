from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

from .config import ACCOUNTS_FILE, OUTPUT_DIR, OUTPUT_FILE_FORMAT, logger
from .models import AccountCredentials


async def get_account_credentials() -> Dict[str, AccountCredentials]:
    try:
        accounts_path = Path(ACCOUNTS_FILE)
        if not accounts_path.exists():
            logger.error("Accounts file %s not found", ACCOUNTS_FILE)
            raise FileNotFoundError(f"Accounts file {ACCOUNTS_FILE} not found")

        with accounts_path.open("r", encoding="utf-8") as fh:
            accounts_data = json.load(fh)

        credentials: Dict[str, AccountCredentials] = {}
        for email_id, account_info in accounts_data.items():
            required_fields = ["refresh_token", "client_id"]
            missing_fields = [field for field in required_fields if not account_info.get(field)]
            if missing_fields:
                logger.warning("Account %s missing required fields: %s", email_id, missing_fields)
                continue
            credentials[email_id] = AccountCredentials(
                email=email_id,
                refresh_token=account_info["refresh_token"],
                client_id=account_info["client_id"],
                tags=account_info.get("tags", []),
            )

        logger.info("Loaded %s account(s) from %s", len(credentials), ACCOUNTS_FILE)
        return credentials
    except json.JSONDecodeError as exc:  # noqa: BLE001
        logger.error("Invalid JSON in accounts file: %s", exc)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error getting account credentials: %s", exc)
        raise


def ensure_output_directory() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_emails(email_id: str, date_suffix: str, emails: list[dict[str, object]]) -> str:
    output_file = os.path.join(
        OUTPUT_DIR,
        OUTPUT_FILE_FORMAT.format(email_id=email_id.replace("@", "_at_"), date=date_suffix),
    )
    with open(output_file, "w", encoding="utf-8") as fh:
        json.dump(emails, fh, indent=2, ensure_ascii=False)
    logger.info("Saved %s emails to %s", len(emails), output_file)
    return output_file


__all__ = ["ensure_output_directory", "get_account_credentials", "save_emails"]
