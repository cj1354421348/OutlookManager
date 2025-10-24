from __future__ import annotations

import asyncio
from datetime import datetime

from .config import logger
from .fetcher import list_emails
from .imap_pool import IMAPConnectionPool
from .storage import ensure_output_directory, get_account_credentials, save_emails


async def run() -> None:
    try:
        ensure_output_directory()
        accounts = await get_account_credentials()
        if not accounts:
            logger.error("No valid accounts found")
            return

        logger.info("Processing %s accounts", len(accounts))
        imap_pool = IMAPConnectionPool()
        current_date = datetime.now().strftime("%Y%m%d")

        for email_id, credentials in accounts.items():
            try:
                logger.info("Processing account: %s", email_id)
                emails = await list_emails(imap_pool, credentials)
                save_emails(email_id, current_date, emails)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to process account %s: %s", email_id, exc)
                continue

        await imap_pool.close_all_connections()
    except Exception as exc:  # noqa: BLE001
        logger.error("Error in run function: %s", exc)


def main() -> None:
    logger.info("Starting batch email retrieval")
    asyncio.run(run())
    logger.info("Batch email retrieval completed")


__all__ = ["main", "run"]
