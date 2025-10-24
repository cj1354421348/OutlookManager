from __future__ import annotations

import copy
import json
import re
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from typing import Dict, Tuple

import pymysql
from pymysql.cursors import DictCursor

from app.config import (
    ACCOUNTS_DB_HOST,
    ACCOUNTS_DB_NAME,
    ACCOUNTS_DB_PASSWORD,
    ACCOUNTS_DB_PORT,
    ACCOUNTS_DB_TABLE,
    ACCOUNTS_DB_USER,
    ACCOUNTS_SYNC_CONFLICT,
    logger,
)

_sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="accounts-sync")


@dataclass(slots=True)
class SyncReport:
    message: str
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    marked_deleted: int = 0

    def to_dict(self) -> Dict[str, int | str]:
        return {
            "message": self.message,
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "skipped": self.skipped,
            "marked_deleted": self.marked_deleted,
        }


class AccountSynchronizer:
    _TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
    _SUPPORTED_CONFLICT_STRATEGIES = {"prefer_local", "prefer_remote"}

    def __init__(self) -> None:
        self._conflict_strategy = self._normalise_conflict_strategy(ACCOUNTS_SYNC_CONFLICT)
        self._table_name = self._normalise_table_name(ACCOUNTS_DB_TABLE)
        self._schema_ready = False

    @property
    def is_enabled(self) -> bool:
        return all([ACCOUNTS_DB_HOST, ACCOUNTS_DB_USER, ACCOUNTS_DB_PASSWORD, ACCOUNTS_DB_NAME])

    @property
    def conflict_strategy(self) -> str:
        return self._conflict_strategy

    def sync_file_to_db(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto") -> SyncReport:
        if not self.is_enabled:
            raise RuntimeError("数据库同步未配置")

        connection = self._connect()
        added = updated = marked_deleted = 0

        try:
            self._ensure_schema(connection)

            with connection.cursor(DictCursor) as cursor:
                cursor.execute(f"SELECT email, checksum, is_deleted, tags FROM `{self._table_name}`")
                existing = {row["email"]: row for row in cursor.fetchall()}

                current_emails = set(accounts.keys())

                for email, payload in accounts.items():
                    normalised_payload = self._normalise_payload(payload)
                    serialised = self._serialise_payload(normalised_payload)
                    tags_serialised = self._serialise_tags(normalised_payload.get("tags", []))
                    checksum = self._checksum(serialised)

                    if email not in existing:
                        cursor.execute(
                            f"""
                            INSERT INTO `{self._table_name}` (email, data, checksum, tags, is_deleted, source)
                            VALUES (%s, %s, %s, %s, 0, %s)
                            """,
                            (email, serialised, checksum, tags_serialised, source),
                        )
                        added += 1
                        continue

                    row = existing[email]
                    if row["checksum"] != checksum or row["is_deleted"]:
                        cursor.execute(
                            f"""
                            UPDATE `{self._table_name}`
                            SET data = %s,
                                checksum = %s,
                                tags = %s,
                                is_deleted = 0,
                                source = %s
                            WHERE email = %s
                            """,
                            (serialised, checksum, tags_serialised, source, email),
                        )
                        updated += 1

                for email, row in existing.items():
                    if email in current_emails or row["is_deleted"]:
                        continue
                    cursor.execute(
                        f"""
                        UPDATE `{self._table_name}`
                        SET is_deleted = 1,
                            tags = %s,
                            source = %s
                        WHERE email = %s
                        """,
                        (self._serialise_tags([]), source, email),
                    )
                    marked_deleted += 1

            connection.commit()
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            logger.exception("同步 accounts.json 到数据库失败: %s", exc)
            raise
        finally:
            connection.close()

        message = f"同步完成：新增 {added}，更新 {updated}，标记删除 {marked_deleted}"
        return SyncReport(message=message, added=added, updated=updated, marked_deleted=marked_deleted)

    def enqueue_file_to_db(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto") -> Future | None:
        if not self.is_enabled:
            return None
        snapshot = copy.deepcopy(accounts)
        future = _sync_executor.submit(self.sync_file_to_db, snapshot, source=source)
        future.add_done_callback(self._log_async_result)
        return future

    def sync_db_to_file(self, local_accounts: Dict[str, Dict[str, object]]) -> Tuple[Dict[str, Dict[str, object]], SyncReport, bool]:
        if not self.is_enabled:
            raise RuntimeError("数据库同步未配置")

        connection = self._connect()

        try:
            self._ensure_schema(connection)
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(f"SELECT email, data, checksum, is_deleted, tags FROM `{self._table_name}`")
                rows = cursor.fetchall()
        finally:
            connection.close()

        remote_accounts: Dict[str, Dict[str, object]] = {}
        for row in rows:
            try:
                payload = json.loads(row["data"]) if row["data"] else {}
            except json.JSONDecodeError:
                logger.warning("数据库中的账户 %s 数据非法，跳过", row["email"])
                continue
            tags_from_column = self._deserialise_tags(row.get("tags"))
            if tags_from_column:
                payload["tags"] = tags_from_column
            elif "tags" not in payload:
                payload["tags"] = []
            remote_accounts[row["email"]] = {
                "data": self._normalise_payload(payload),
                "checksum": row["checksum"],
                "is_deleted": bool(row["is_deleted"]),
            }

        merged_accounts, report, changed = self._merge_remote_into_local(local_accounts, remote_accounts)
        return merged_accounts, report, changed

    def _merge_remote_into_local(
        self,
        local_accounts: Dict[str, Dict[str, object]],
        remote_accounts: Dict[str, Dict[str, object]],
    ) -> Tuple[Dict[str, Dict[str, object]], SyncReport, bool]:
        merged = dict(local_accounts)
        added = updated = removed = skipped = 0
        changed = False

        for email, record in remote_accounts.items():
            remote_payload = record["data"]
            remote_checksum = record["checksum"]
            is_deleted = record["is_deleted"]

            local_payload = merged.get(email)
            local_checksum = (
                self._checksum(self._serialise_payload(self._normalise_payload(local_payload)))
                if local_payload is not None
                else None
            )

            if is_deleted:
                if email not in merged:
                    continue
                if self._conflict_strategy == "prefer_local":
                    skipped += 1
                    continue
                merged.pop(email)
                removed += 1
                changed = True
                continue

            if email not in merged:
                merged[email] = remote_payload
                added += 1
                changed = True
                continue

            if local_checksum == remote_checksum:
                continue

            if self._conflict_strategy == "prefer_local":
                skipped += 1
                continue

            merged[email] = remote_payload
            updated += 1
            changed = True

        message = (
            "同步完成：新增 {added}，更新 {updated}，移除 {removed}，跳过 {skipped}"
        ).format(added=added, updated=updated, removed=removed, skipped=skipped)

        return merged, SyncReport(
            message=message,
            added=added,
            updated=updated,
            removed=removed,
            skipped=skipped,
        ), changed

    def _ensure_schema(self, connection: "pymysql.connections.Connection") -> None:
        if self._schema_ready:
            return

        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{self._table_name}` (
                    `email` VARCHAR(255) NOT NULL PRIMARY KEY,
                    `data` LONGTEXT NOT NULL,
                    `checksum` CHAR(64) NOT NULL,
                    `tags` LONGTEXT,
                    `is_deleted` TINYINT(1) NOT NULL DEFAULT 0,
                    `source` VARCHAR(32) NOT NULL DEFAULT 'unknown',
                    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(f"SHOW COLUMNS FROM `{self._table_name}` LIKE 'tags'")
            has_tags_column = cursor.fetchone()
            if not has_tags_column:
                cursor.execute(f"ALTER TABLE `{self._table_name}` ADD COLUMN `tags` LONGTEXT")
                cursor.execute(
                    f"UPDATE `{self._table_name}` SET `tags` = %s WHERE `tags` IS NULL",
                    (self._serialise_tags([]),),
                )
        connection.commit()
        self._schema_ready = True

    @staticmethod
    def _normalise_payload(payload: Dict[str, object] | None) -> Dict[str, object]:
        if payload is None:
            return {}
        normalised = dict(payload)
        if "tags" not in normalised or normalised["tags"] is None:
            normalised["tags"] = []
        else:
            tags = normalised["tags"]
            if isinstance(tags, list):
                cleaned_tags: list[str] = []
                for tag in tags:
                    if tag is None:
                        continue
                    tag_text = str(tag).strip()
                    if not tag_text:
                        continue
                    cleaned_tags.append(tag_text)
                normalised["tags"] = cleaned_tags
            else:
                tag_text = str(tags).strip()
                normalised["tags"] = [tag_text] if tag_text else []
        return normalised

    @staticmethod
    def _serialise_tags(tags: object) -> str:
        if isinstance(tags, list):
            cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
        elif tags is None:
            cleaned = []
        else:
            cleaned = [str(tags).strip()] if str(tags).strip() else []
        return json.dumps(cleaned, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _deserialise_tags(raw: object) -> list[str]:
        if raw is None or raw == "":
            return []
        if isinstance(raw, list):
            return [str(tag).strip() for tag in raw if str(tag).strip()]
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except Exception:  # noqa: BLE001
                return []
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.split(",") if raw else []
            if isinstance(parsed, list):
                return [str(tag).strip() for tag in parsed if str(tag).strip()]
            return [raw.strip()] if raw.strip() else []
        return []

    @staticmethod
    def _serialise_payload(payload: Dict[str, object]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _checksum(serialised_payload: str | Dict[str, object] | None) -> str | None:
        if serialised_payload is None:
            return None
        if isinstance(serialised_payload, str):
            data = serialised_payload
        else:
            data = json.dumps(serialised_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(data.encode("utf-8")).hexdigest()

    def _connect(self) -> "pymysql.connections.Connection":
        return pymysql.connect(
            host=ACCOUNTS_DB_HOST,
            port=ACCOUNTS_DB_PORT,
            user=ACCOUNTS_DB_USER,
            password=ACCOUNTS_DB_PASSWORD,
            database=ACCOUNTS_DB_NAME,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=DictCursor,
        )

    def _normalise_conflict_strategy(self, strategy: str | None) -> str:
        if not strategy:
            return "prefer_local"
        normalised = strategy.strip().lower()
        if normalised not in self._SUPPORTED_CONFLICT_STRATEGIES:
            logger.warning("未知的冲突策略 %s，已回退为 prefer_local", strategy)
            return "prefer_local"
        return normalised

    def _normalise_table_name(self, table_name: str | None) -> str:
        if table_name and self._TABLE_NAME_PATTERN.match(table_name):
            return table_name
        if table_name:
            logger.warning("非法的表名 %s，已回退为 account_backups", table_name)
        return "account_backups"

    @staticmethod
    def _log_async_result(future: Future) -> None:
        try:
            report = future.result()
            logger.info("后台同步完成：%s", report.message)
        except Exception as exc:  # noqa: BLE001
            logger.error("后台同步失败: %s", exc, exc_info=True)


__all__ = ["AccountSynchronizer", "SyncReport"]
