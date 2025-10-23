from __future__ import annotations

import json
import threading
from contextlib import suppress
from pathlib import Path
from typing import Dict

from fastapi import HTTPException
from filelock import FileLock

from app.config import logger

from .sync import AccountSynchronizer, SyncReport


class AccountRepository:
    def __init__(self, file_path: str, synchronizer: AccountSynchronizer | None = None) -> None:
        self._path = Path(file_path)
        self._lock = threading.RLock()
        self._file_lock = FileLock(str(self._path) + ".lock")
        self._synchronizer = synchronizer

    def read_all(self) -> Dict[str, Dict[str, object]]:
        if not self._path.exists():
            return {}
        try:
            with self._file_lock:
                with self._path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in accounts file: %s", exc)
            raise HTTPException(status_code=500, detail="Accounts file format error")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read accounts file: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to read accounts file")

    def write_all(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto") -> None:
        self._write_to_disk(accounts)
        self._sync_to_database(accounts, source=source)

    def save_account(self, email_id: str, data: Dict[str, object]) -> None:
        with self._lock:
            accounts = self.read_all()
            accounts[email_id] = data
            self._write_to_disk_locked(accounts)
        self._sync_to_database(accounts, source="mutation")

    def delete_account(self, email_id: str) -> None:
        with self._lock:
            accounts = self.read_all()
            if email_id not in accounts:
                raise HTTPException(status_code=404, detail="Account not found")
            accounts.pop(email_id)
            self._write_to_disk_locked(accounts)
        self._sync_to_database(accounts, source="mutation")

    def sync_to_database(self, *, source: str = "manual") -> SyncReport:
        synchronizer = self._require_synchronizer()
        accounts = self.read_all()
        return synchronizer.sync_file_to_db(accounts, source=source)

    def merge_from_database(self) -> tuple[Dict[str, Dict[str, object]], SyncReport, bool]:
        synchronizer = self._require_synchronizer()
        accounts = self.read_all()
        return synchronizer.sync_db_to_file(accounts)

    def _write_to_disk(self, accounts: Dict[str, Dict[str, object]]) -> None:
        with self._lock:
            self._write_to_disk_locked(accounts)

    def _write_to_disk_locked(self, accounts: Dict[str, Dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.parent / (self._path.name + ".tmp")
        try:
            with self._file_lock:
                with tmp_path.open("w", encoding="utf-8") as fh:
                    json.dump(accounts, fh, indent=2, ensure_ascii=False)
                tmp_path.replace(self._path)
        finally:
            with suppress(FileNotFoundError):
                tmp_path.unlink()

    def _sync_to_database(self, accounts: Dict[str, Dict[str, object]], *, source: str) -> None:
        if not self._synchronizer or not self._synchronizer.is_enabled:
            return
        try:
            future = self._synchronizer.enqueue_file_to_db(accounts, source=source)
            if future is None:
                logger.debug("账户数据库同步未启用，跳过")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to enqueue accounts sync job: %s", exc, exc_info=True)

    def _require_synchronizer(self) -> AccountSynchronizer:
        if not self._synchronizer or not self._synchronizer.is_enabled:
            raise RuntimeError("数据库同步未配置")
        return self._synchronizer
