from __future__ import annotations

import copy
import json
import re
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from typing import Dict, Iterable, Set, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import (
    ACCOUNTS_DB_HOST,
    ACCOUNTS_DB_NAME,
    ACCOUNTS_DB_PASSWORD,
    ACCOUNTS_DB_PORT,
    ACCOUNTS_DB_TABLE,
    ACCOUNTS_DB_USER,
    ACCOUNTS_SYNC_CONFLICT,
    DATABASE_URL,
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
        self._tags_table = f"{self._table_name}_tags"
        self._schema_ready = False

    @property
    def is_enabled(self) -> bool:
        # 如果使用 DATABASE_URL，只需要检查它是否存在
        if DATABASE_URL:
            return True
        # 否则检查所有单独的连接参数
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

            with connection.cursor() as cursor:
                cursor.execute(f"SELECT email, checksum, is_deleted, tags, note FROM \"{self._table_name}\"")
                existing = {row["email"]: row for row in cursor.fetchall()}

            normalised_accounts, tags_target = self._prepare_tags_snapshot(accounts)
            current_emails = set(normalised_accounts.keys())
            all_emails_for_tags = set(existing.keys()) | current_emails
            tags_existing = self._fetch_existing_tags(connection, all_emails_for_tags)

            with connection.cursor() as cursor:
                for email, normalised_payload in normalised_accounts.items():
                    serialised = self._serialise_payload(normalised_payload)
                    tags_serialised = self._serialise_tags(normalised_payload.get("tags", []))
                    checksum = self._checksum(serialised)

                    if email not in existing:
                        note_value = normalised_payload.get("note")
                        cursor.execute(
                            f"""
                            INSERT INTO "{self._table_name}" (email, data, checksum, tags, note, is_deleted, source)
                            VALUES (%s, %s, %s, %s, %s, FALSE, %s)
                            """,
                            (email, serialised, checksum, tags_serialised, note_value, source),
                        )
                        added += 1
                        continue

                    row = existing[email]
                    if row["checksum"] != checksum or row["is_deleted"]:
                        note_value = normalised_payload.get("note")
                        cursor.execute(
                            f"""
                            UPDATE "{self._table_name}"
                            SET data = %s,
                                checksum = %s,
                                tags = %s,
                                note = %s,
                                is_deleted = FALSE,
                                source = %s
                            WHERE email = %s
                            """,
                            (serialised, checksum, tags_serialised, note_value, source, email),
                        )
                        updated += 1

                for email, row in existing.items():
                    if email in current_emails or row["is_deleted"]:
                        continue
                    cursor.execute(
                        f"""
                        UPDATE "{self._table_name}"
                        SET is_deleted = TRUE,
                            tags = %s,
                            note = NULL,
                            source = %s
                        WHERE email = %s
                        """,
                        (self._serialise_tags([]), source, email),
                    )
                    marked_deleted += 1

            for email in all_emails_for_tags:
                self._apply_tag_mutations(
                    connection,
                    email,
                    tags_existing.get(email, set()),
                    tags_target.get(email, set()),
                )

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
        tags_map: Dict[str, Set[str]] = {}

        try:
            self._ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT email, data, checksum, is_deleted, tags, note FROM \"{self._table_name}\"")
                rows = cursor.fetchall()
            tags_map = self._fetch_existing_tags(connection, [row["email"] for row in rows])
        finally:
            connection.close()

        remote_accounts: Dict[str, Dict[str, object]] = {}
        for row in rows:
            try:
                payload = json.loads(row["data"]) if row["data"] else {}
            except json.JSONDecodeError:
                logger.warning("数据库中的账户 %s 数据非法，跳过", row["email"])
                continue
            stored_tags = sorted(tags_map.get(row["email"], []))
            tags_from_column = stored_tags or self._deserialise_tags(row.get("tags"))
            if tags_from_column:
                payload["tags"] = tags_from_column
            elif "tags" not in payload:
                payload["tags"] = []
            normalised_payload = self._normalise_payload(payload)
            note_from_column = self._normalise_note_value(row.get("note"))
            if note_from_column is not None:
                normalised_payload["note"] = note_from_column
            combined_checksum = self._checksum(self._serialise_payload(normalised_payload)) or row["checksum"]
            remote_accounts[row["email"]] = {
                "data": normalised_payload,
                "checksum": combined_checksum,
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
                local_entry = merged[email]
                has_changes = False
                if self._merge_tags_from_remote(local_entry, remote_payload):
                    has_changes = True
                if self._merge_note_from_remote(local_entry, remote_payload):
                    has_changes = True
                if has_changes:
                    updated += 1
                    changed = True
                else:
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

    def _ensure_schema(self, connection: "psycopg2.extensions.connection") -> None:
        if self._schema_ready:
            return

        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self._table_name}" (
                    "email" VARCHAR(255) NOT NULL PRIMARY KEY,
                    "data" TEXT NOT NULL,
                    "checksum" CHAR(64) NOT NULL,
                    "tags" TEXT,
                    "note" TEXT,
                    "is_deleted" BOOLEAN NOT NULL DEFAULT FALSE,
                    "source" VARCHAR(32) NOT NULL DEFAULT 'unknown',
                    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{self._table_name}' AND column_name='tags'")
            has_tags_column = cursor.fetchone()
            if not has_tags_column:
                cursor.execute(f"ALTER TABLE \"{self._table_name}\" ADD COLUMN \"tags\" TEXT")
                cursor.execute(
                    f"UPDATE \"{self._table_name}\" SET \"tags\" = %s WHERE \"tags\" IS NULL",
                    (self._serialise_tags([]),),
                )
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{self._table_name}' AND column_name='note'")
            has_note_column = cursor.fetchone()
            note_column_added = False
            if not has_note_column:
                cursor.execute(f"ALTER TABLE \"{self._table_name}\" ADD COLUMN \"note\" TEXT")
                note_column_added = True
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self._tags_table}" (
                    "email" VARCHAR(255) NOT NULL,
                    "tag" VARCHAR(255) NOT NULL,
                    PRIMARY KEY ("email", "tag")
                )
                """
            )
            cursor.execute(f"CREATE INDEX IF NOT EXISTS \"idx_{self._tags_table}_email\" ON \"{self._tags_table}\" (\"email\")")
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM \"{self._tags_table}\"")
            tag_count_row = cursor.fetchone() or {"cnt": 0}
            if (tag_count_row.get("cnt") or 0) == 0:
                cursor.execute(f"SELECT email, tags FROM \"{self._table_name}\" WHERE tags IS NOT NULL AND tags != ''")
                seed_rows = cursor.fetchall()
                seed_pairs: list[tuple[str, str]] = []
                for seed in seed_rows:
                    email = seed.get("email")
                    if not email:
                        continue
                    for tag in self._deserialise_tags(seed.get("tags")):
                        if tag:
                            seed_pairs.append((email, tag))
                for chunk in self._chunked(seed_pairs, 500):
                    cursor.executemany(
                        f"""
                        INSERT INTO "{self._tags_table}" (email, tag)
                        VALUES (%s, %s)
                        ON CONFLICT (email, tag) DO NOTHING
                        """,
                        chunk,
                    )
        connection.commit()
        self._schema_ready = True

        if note_column_added:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT email, data FROM \"{self._table_name}\"")
                rows = cursor.fetchall()
                for row in rows:
                    email = row.get("email")
                    data_raw = row.get("data")
                    if not email or not data_raw:
                        continue
                    try:
                        payload = json.loads(data_raw)
                    except json.JSONDecodeError:
                        continue
                    note_value = self._normalise_note_value(payload.get("note"))
                    if note_value:
                        cursor.execute(
                            f"UPDATE \"{self._table_name}\" SET \"note\" = %s WHERE email = %s",
                            (note_value, email),
                        )
            connection.commit()

    def _prepare_tags_snapshot(
        self,
        accounts: Dict[str, Dict[str, object]],
    ) -> tuple[Dict[str, Dict[str, object]], Dict[str, Set[str]]]:
        normalised_accounts: Dict[str, Dict[str, object]] = {}
        tags_snapshot: Dict[str, Set[str]] = {}
        for email, payload in accounts.items():
            normalised = self._normalise_payload(payload)
            normalised_accounts[email] = normalised
            tags_snapshot[email] = set(normalised.get("tags", []))
        return normalised_accounts, tags_snapshot

    def _fetch_existing_tags(
        self,
        connection: "psycopg2.extensions.connection",
        emails: Iterable[str],
    ) -> Dict[str, Set[str]]:
        email_list = [email for email in dict.fromkeys(emails) if email]
        if not email_list:
            return {}

        tags_map: Dict[str, Set[str]] = {email: set() for email in email_list}
        with connection.cursor() as cursor:
            for chunk in self._chunked(email_list, 500):
                placeholders = ",".join(["%s"] * len(chunk))
                cursor.execute(
                    f"SELECT email, tag FROM \"{self._tags_table}\" WHERE email IN ({placeholders})",
                    tuple(chunk),
                )
                for row in cursor.fetchall():
                    email = row.get("email")
                    tag = row.get("tag")
                    if not email or not tag:
                        continue
                    tags_map.setdefault(email, set()).add(tag)
        return tags_map

    def _apply_tag_mutations(
        self,
        connection: "psycopg2.extensions.connection",
        email: str,
        existing: Set[str] | None,
        target: Set[str] | None,
    ) -> None:
        existing_tags = existing or set()
        target_tags = target or set()
        if existing_tags == target_tags:
            return

        to_add = sorted(target_tags - existing_tags)
        to_remove = sorted(existing_tags - target_tags)

        if to_add:
            payload = [(email, tag) for tag in to_add]
            with connection.cursor() as cursor:
                for chunk in self._chunked(payload, 500):
                    cursor.executemany(
                        f"""
                        INSERT INTO "{self._tags_table}" (email, tag)
                        VALUES (%s, %s)
                        ON CONFLICT (email, tag) DO NOTHING
                        """,
                        chunk,
                    )

        if to_remove:
            with connection.cursor() as cursor:
                for chunk in self._chunked(to_remove, 500):
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(
                        f"DELETE FROM \"{self._tags_table}\" WHERE email = %s AND tag IN ({placeholders})",
                        (email, *chunk),
                    )

    @staticmethod
    def _chunked(items: Iterable[object], size: int) -> Iterable[list[object]]:
        batch: list[object] = []
        for item in items:
            batch.append(item)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch

    @staticmethod
    def _merge_tags_from_remote(local_payload: Dict[str, object], remote_payload: Dict[str, object]) -> bool:
        remote_tags = remote_payload.get("tags", []) or []
        local_tags = local_payload.get("tags", []) or []
        normalised_remote = [str(tag).strip() for tag in remote_tags if str(tag).strip()]
        normalised_local = [str(tag).strip() for tag in local_tags if str(tag).strip()]
        if sorted(normalised_remote) == sorted(normalised_local):
            return False
        local_payload["tags"] = normalised_remote
        return True

    def _merge_note_from_remote(self, local_payload: Dict[str, object], remote_payload: Dict[str, object]) -> bool:
        remote_note = self._normalise_note_value(remote_payload.get("note"))
        local_note = self._normalise_note_value(local_payload.get("note"))
        if local_note == remote_note:
            return False
        if remote_note is None:
            local_payload.pop("note", None)
        else:
            local_payload["note"] = remote_note
        return True

    def _normalise_payload(self, payload: Dict[str, object] | None) -> Dict[str, object]:
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

        if "note" in normalised:
            note_value = self._normalise_note_value(normalised.get("note"))
            if note_value is None:
                normalised.pop("note", None)
            else:
                normalised["note"] = note_value

        return normalised

    @staticmethod
    def _normalise_note_value(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        stripped = text.strip()
        return stripped if stripped else None

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

    def _connect(self) -> "psycopg2.extensions.connection":
        if DATABASE_URL:
            # 使用完整的 DATABASE_URL 连接字符串
            return psycopg2.connect(
                DATABASE_URL,
                sslmode='require',  # Neon.tech 强制要求 SSL 连接
                cursor_factory=RealDictCursor,
            )
        else:
            # 使用单独的连接参数（向后兼容）
            return psycopg2.connect(
                host=ACCOUNTS_DB_HOST,
                port=ACCOUNTS_DB_PORT,
                user=ACCOUNTS_DB_USER,
                password=ACCOUNTS_DB_PASSWORD,
                database=ACCOUNTS_DB_NAME,
                sslmode='require',  # Neon.tech 强制要求 SSL 连接
                cursor_factory=RealDictCursor,
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
