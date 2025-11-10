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
                    # 详细日志：推送前的数据状态
                    logger.debug("=== 推送账户 %s ===", email)
                    logger.debug("推送前标准化数据: %s", json.dumps(normalised_payload, indent=2, ensure_ascii=False))
                    
                    serialised = self._serialise_payload(normalised_payload)
                    tags_serialised = self._serialise_tags(normalised_payload.get("tags", []))
                    checksum = self._checksum(serialised)
                    
                    # 详细日志：推送时的序列化和校验和
                    logger.debug("推送序列化结果: %s", serialised)
                    logger.debug("推送计算校验和: %s", checksum)
                    
                    # 记录状态字段的类型和值变化
                    if "status" in normalised_payload:
                        logger.debug("推送状态字段: %s (类型: %s)", normalised_payload.get("status"), type(normalised_payload.get("status")))
                    if "status_updated_at" in normalised_payload:
                        logger.debug("推送状态更新时间: %s (类型: %s)", normalised_payload.get("status_updated_at"), type(normalised_payload.get("status_updated_at")))
                    if "token_failures" in normalised_payload:
                        token_failures = normalised_payload.get("token_failures")
                        if isinstance(token_failures, dict) and "count" in token_failures:
                            logger.debug("推送令牌失败次数: %s (类型: %s, count: %s)", token_failures, type(token_failures), token_failures.get("count"))
                        else:
                            logger.debug("推送令牌失败次数: %s (类型: %s)", token_failures, type(token_failures))

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
                        logger.debug("更新账户 %s：校验和不同 (本地=%s, 远程=%s) 或已删除 (is_deleted=%s)",
                                   email, row["checksum"], checksum, row["is_deleted"])
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
                    else:
                        logger.debug("跳过账户 %s：校验和相同且未删除 (checksum=%s)", email, checksum)

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
                
            # 详细日志：拉取时的原始数据
            logger.debug("=== 拉取账户 %s ===", row["email"])
            logger.debug("从数据库读取原始数据: %s", row["data"])
            logger.debug("JSON解析后数据: %s", json.dumps(payload, indent=2, ensure_ascii=False))
            logger.debug("数据库中存储的校验和: %s", row["checksum"])
            
            stored_tags = sorted(tags_map.get(row["email"], []))
            tags_from_column = stored_tags or self._deserialise_tags(row.get("tags"))
            if tags_from_column:
                payload["tags"] = tags_from_column
            elif "tags" not in payload:
                payload["tags"] = []
                
            # 详细日志：标准化前的数据
            logger.debug("标准化前数据: %s", json.dumps(payload, indent=2, ensure_ascii=False))
            
            normalised_payload = self._normalise_payload(payload)
            note_from_column = self._normalise_note_value(row.get("note"))
            if note_from_column is not None:
                normalised_payload["note"] = note_from_column
            
            # 详细日志：标准化后的数据
            logger.debug("标准化后数据: %s", json.dumps(normalised_payload, indent=2, ensure_ascii=False))
            
            # 确保状态字段被正确处理
            logger.debug("处理账户 %s 的状态字段", row["email"])
            if "status" in normalised_payload:
                logger.debug("标准化后状态: %s (类型: %s)", normalised_payload.get("status"), type(normalised_payload.get("status")))
            if "status_updated_at" in normalised_payload:
                logger.debug("标准化后状态更新时间: %s (类型: %s)", normalised_payload.get("status_updated_at"), type(normalised_payload.get("status_updated_at")))
            if "status_reason" in normalised_payload:
                logger.debug("标准化后状态原因: %s (类型: %s)", normalised_payload.get("status_reason"), type(normalised_payload.get("status_reason")))
            if "token_failures" in normalised_payload:
                token_failures = normalised_payload.get("token_failures")
                if isinstance(token_failures, dict) and "count" in token_failures:
                    logger.debug("标准化后令牌失败次数: %s (类型: %s, count: %s)", token_failures, type(token_failures), token_failures.get("count"))
                else:
                    logger.debug("标准化后令牌失败次数: %s (类型: %s)", token_failures, type(token_failures))
            
            serialised_payload = self._serialise_payload(normalised_payload)
            calculated_checksum = self._checksum(serialised_payload)
            
            # 详细日志：记录校验和计算的详细过程
            logger.debug("账户 %s 序列化数据: %s", row["email"], serialised_payload)
            logger.debug("账户 %s 序列化数据长度: %d", row["email"], len(serialised_payload))
            
            # 如果校验和计算失败，记录错误而不是使用数据库中的校验和
            if calculated_checksum is None:
                logger.error("账户 %s 校验和计算失败，使用数据库中的校验和作为备用", row["email"])
                combined_checksum = row["checksum"]
            else:
                combined_checksum = calculated_checksum
                logger.debug("账户 %s 校验和计算成功: %s", row["email"], calculated_checksum)
            
            # 详细日志记录，用于调试跳过原因
            logger.debug("账户 %s 计算的校验和: %s, 数据库校验和: %s",
                       row["email"], combined_checksum, row["checksum"])
            
            # 记录标准化前后的字段变化
            if "status" in normalised_payload:
                logger.debug("拉取标准化后状态字段: %s (类型: %s)", normalised_payload.get("status"), type(normalised_payload.get("status")))
            if "status_updated_at" in normalised_payload:
                logger.debug("拉取标准化后状态更新时间: %s (类型: %s)", normalised_payload.get("status_updated_at"), type(normalised_payload.get("status_updated_at")))
            if "token_failures" in normalised_payload:
                token_failures = normalised_payload.get("token_failures")
                if isinstance(token_failures, dict) and "count" in token_failures:
                    logger.debug("拉取标准化后令牌失败次数: %s (类型: %s, count: %s)", token_failures, type(token_failures), token_failures.get("count"))
                else:
                    logger.debug("拉取标准化后令牌失败次数: %s (类型: %s)", token_failures, type(token_failures))
            
            remote_accounts[row["email"]] = {
                "data": normalised_payload,
                "checksum": combined_checksum,
                "is_deleted": bool(row["is_deleted"]),
            }

        logger.debug("开始合并远程账户数据到本地，远程账户数量: %d", len(remote_accounts))
        merged_accounts, report, changed = self._merge_remote_into_local(local_accounts, remote_accounts)
        logger.debug("合并完成，报告: %s, 是否有变更: %s", report.message, changed)
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
            
            logger.debug("处理账户 %s，远程状态: %s", email, "已删除" if is_deleted else "正常")
            if "status" in remote_payload:
                logger.debug("远程账户 %s 状态: %s", email, remote_payload.get("status"))

            local_payload = merged.get(email)
            if local_payload is not None:
                # 详细日志：本地数据的处理过程
                logger.debug("=== 账户 %s 本地数据处理 ===", email)
                logger.debug("本地原始数据: %s", json.dumps(local_payload, indent=2, ensure_ascii=False))
                
                normalised_local = self._normalise_payload(local_payload)
                logger.debug("本地标准化后数据: %s", json.dumps(normalised_local, indent=2, ensure_ascii=False))
                
                serialised_local = self._serialise_payload(normalised_local)
                local_checksum = self._checksum(serialised_local)
                
                logger.debug("账户 %s 本地序列化数据: %s", email, serialised_local)
                logger.debug("账户 %s 本地序列化数据长度: %d", email, len(serialised_local))
                logger.debug("账户 %s 本地校验和: %s", email, local_checksum)
                
                # 详细比较状态字段
                if "status" in normalised_local:
                    logger.debug("本地状态: %s (类型: %s)", normalised_local.get("status"), type(normalised_local.get("status")))
                if "status" in remote_payload:
                    logger.debug("远程状态: %s (类型: %s)", remote_payload.get("status"), type(remote_payload.get("status")))
                    
                # 比较状态更新时间
                if "status_updated_at" in normalised_local:
                    logger.debug("本地状态更新时间: %s (类型: %s)", normalised_local.get("status_updated_at"), type(normalised_local.get("status_updated_at")))
                if "status_updated_at" in remote_payload:
                    logger.debug("远程状态更新时间: %s (类型: %s)", remote_payload.get("status_updated_at"), type(remote_payload.get("status_updated_at")))
                    
                # 比较令牌失败次数
                if "token_failures" in normalised_local:
                    local_token_failures = normalised_local.get("token_failures")
                    if isinstance(local_token_failures, dict) and "count" in local_token_failures:
                        logger.debug("本地令牌失败次数: %s (类型: %s, count: %s)", local_token_failures, type(local_token_failures), local_token_failures.get("count"))
                    else:
                        logger.debug("本地令牌失败次数: %s (类型: %s)", local_token_failures, type(local_token_failures))
                if "token_failures" in remote_payload:
                    remote_token_failures = remote_payload.get("token_failures")
                    if isinstance(remote_token_failures, dict) and "count" in remote_token_failures:
                        logger.debug("远程令牌失败次数: %s (类型: %s, count: %s)", remote_token_failures, type(remote_token_failures), remote_token_failures.get("count"))
                    else:
                        logger.debug("远程令牌失败次数: %s (类型: %s)", remote_token_failures, type(remote_token_failures))
            else:
                local_checksum = None

            if is_deleted:
                if email not in merged:
                    logger.debug("跳过账户 %s：远程已删除但本地不存在", email)
                    continue
                if self._conflict_strategy == "prefer_local":
                    logger.debug("跳过账户 %s：远程已删除但策略为 prefer_local", email)
                    skipped += 1
                    continue
                logger.debug("删除账户 %s：远程已删除且策略为 prefer_remote", email)
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
                logger.debug("跳过账户 %s：校验和相同 (本地=%s, 远程=%s)", email, local_checksum, remote_checksum)
                
                # 即使校验和相同，也检查关键字段是否有差异
                if local_payload and remote_payload:
                    if self._has_critical_field_differences(email, local_payload, remote_payload):
                        logger.warning("账户 %s 检测到关键字段差异，但校验和相同，强制更新", email)
                        # 强制更新，即使校验和相同
                        if self._conflict_strategy == "prefer_remote":
                            merged[email] = remote_payload
                            updated += 1
                            changed = True
                            logger.debug("使用远程数据覆盖本地账户 %s（关键字段差异）", email)
                        else:
                            # prefer_local 策略下，合并远程的关键字段
                            local_entry = merged[email]
                            has_changes = False
                            if self._merge_tags_from_remote(local_entry, remote_payload):
                                has_changes = True
                            if self._merge_note_from_remote(local_entry, remote_payload):
                                has_changes = True
                            if self._merge_status_from_remote(local_entry, remote_payload):
                                has_changes = True
                            if has_changes:
                                updated += 1
                                changed = True
                                logger.debug("合并远程关键字段到本地账户 %s", email)
                
                continue

            if self._conflict_strategy == "prefer_local":
                local_entry = merged[email]
                has_changes = False
                if self._merge_tags_from_remote(local_entry, remote_payload):
                    has_changes = True
                if self._merge_note_from_remote(local_entry, remote_payload):
                    has_changes = True
                # 添加状态字段合并逻辑
                if self._merge_status_from_remote(local_entry, remote_payload):
                    has_changes = True
                if has_changes:
                    updated += 1
                    changed = True
                else:
                    logger.debug("跳过账户 %s：prefer_local 策略下无实质性变更", email)
                    skipped += 1
                continue

            logger.debug("使用远程数据覆盖本地账户 %s", email)
            if "status" in remote_payload:
                logger.debug("覆盖后账户 %s 状态: %s", email, remote_payload.get("status"))
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

    def _merge_status_from_remote(self, local_payload: Dict[str, object], remote_payload: Dict[str, object]) -> bool:
        """合并状态字段，确保状态信息不会丢失"""
        has_changes = False
        
        # 处理 status 字段
        local_status = local_payload.get("status")
        remote_status = remote_payload.get("status")
        if local_status != remote_status:
            if remote_status is not None:
                local_payload["status"] = remote_status
                has_changes = True
                logger.debug("更新状态字段: %s -> %s", local_status, remote_status)
        
        # 处理 status_updated_at 字段
        local_status_updated_at = local_payload.get("status_updated_at")
        remote_status_updated_at = remote_payload.get("status_updated_at")
        if local_status_updated_at != remote_status_updated_at:
            if remote_status_updated_at is not None:
                local_payload["status_updated_at"] = remote_status_updated_at
                has_changes = True
                logger.debug("更新状态更新时间: %s -> %s", local_status_updated_at, remote_status_updated_at)
        
        # 处理 status_reason 字段
        local_status_reason = local_payload.get("status_reason")
        remote_status_reason = remote_payload.get("status_reason")
        if local_status_reason != remote_status_reason:
            if remote_status_reason is not None:
                local_payload["status_reason"] = remote_status_reason
                has_changes = True
                logger.debug("更新状态原因: %s -> %s", local_status_reason, remote_status_reason)
        
        # 处理 token_failures 字段
        local_token_failures = local_payload.get("token_failures")
        remote_token_failures = remote_payload.get("token_failures")
        
        # 提取本地的 count 值
        local_count = 0
        if isinstance(local_token_failures, dict) and "count" in local_token_failures:
            try:
                local_count = int(local_token_failures["count"]) if local_token_failures["count"] is not None else 0
            except (ValueError, TypeError):
                local_count = 0
        elif isinstance(local_token_failures, (int, float, str)):
            try:
                local_count = int(local_token_failures) if local_token_failures is not None else 0
            except (ValueError, TypeError):
                local_count = 0
        
        # 提取远程的 count 值
        remote_count = 0
        if isinstance(remote_token_failures, dict) and "count" in remote_token_failures:
            try:
                remote_count = int(remote_token_failures["count"]) if remote_token_failures["count"] is not None else 0
            except (ValueError, TypeError):
                remote_count = 0
        elif isinstance(remote_token_failures, (int, float, str)):
            try:
                remote_count = int(remote_token_failures) if remote_token_failures is not None else 0
            except (ValueError, TypeError):
                remote_count = 0
        
        # 如果 count 值不同，更新本地 token_failures
        if local_count != remote_count:
            # 如果远程是字典格式，直接使用
            if isinstance(remote_token_failures, dict):
                local_payload["token_failures"] = remote_token_failures
            else:
                # 否则创建新的字典格式
                local_payload["token_failures"] = {"count": remote_count}
            has_changes = True
            logger.debug("更新令牌失败次数: %s -> %s", local_count, remote_count)
        
        return has_changes

    def _normalise_payload(self, payload: Dict[str, object] | None) -> Dict[str, object]:
        if payload is None:
            return {}
        normalised = dict(payload)
        
        # 添加调试日志：记录原始状态字段
        original_status = normalised.get("status")
        original_status_updated_at = normalised.get("status_updated_at")
        original_status_reason = normalised.get("status_reason")
        original_token_failures = normalised.get("token_failures")
        
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

        # 处理状态字段
        if "status" in normalised:
            status_value = normalised.get("status")
            if status_value is None:
                normalised.pop("status", None)
            else:
                normalised["status"] = str(status_value).strip()
        
        if "status_updated_at" in normalised:
            status_updated_at = normalised.get("status_updated_at")
            if status_updated_at is None:
                normalised.pop("status_updated_at", None)
            else:
                # 更严格的时间戳处理，确保格式一致性
                status_str = str(status_updated_at).strip()
                # 尝试标准化时间戳格式，去除可能的毫秒精度差异
                if status_str:
                    # 如果是数字时间戳，转换为字符串
                    try:
                        # 尝试解析为浮点数时间戳
                        timestamp_float = float(status_str)
                        # 转换为整数秒，确保推送和拉取时格式一致
                        normalised["status_updated_at"] = str(int(timestamp_float))
                    except (ValueError, TypeError):
                        # 如果不是数字，保持原始字符串但去除多余空格
                        normalised["status_updated_at"] = status_str
                else:
                    normalised.pop("status_updated_at", None)
        
        if "status_reason" in normalised:
            status_reason = normalised.get("status_reason")
            if status_reason is None:
                normalised.pop("status_reason", None)
            else:
                normalised["status_reason"] = str(status_reason).strip()
        
        if "token_failures" in normalised:
            token_failures = normalised.get("token_failures")
            if token_failures is None:
                normalised.pop("token_failures", None)
            else:
                # token_failures 应该是一个字典对象，包含 count 等字段
                if isinstance(token_failures, dict):
                    # 确保字典中的 count 字段是整数
                    if "count" in token_failures:
                        try:
                            count_value = token_failures["count"]
                            if isinstance(count_value, str):
                                count_value = count_value.strip()
                                token_failures["count"] = int(count_value) if count_value else 0
                            else:
                                token_failures["count"] = int(count_value) if count_value is not None else 0
                        except (ValueError, TypeError):
                            logger.warning("无法解析 token_failures.count 值 %s，设置为 0", count_value)
                            token_failures["count"] = 0
                    normalised["token_failures"] = token_failures
                elif isinstance(token_failures, (int, float, str)):
                    # 如果是数字或字符串，转换为字典格式
                    try:
                        count_value = int(token_failures) if token_failures is not None else 0
                        normalised["token_failures"] = {"count": count_value}
                        logger.debug("将 token_failures 从 %s 转换为字典格式: %s", token_failures, normalised["token_failures"])
                    except (ValueError, TypeError):
                        logger.warning("无法解析 token_failures 值 %s，设置为字典格式 {\"count\": 0}", token_failures)
                        normalised["token_failures"] = {"count": 0}
                else:
                    # 其他类型，设置为默认字典格式
                    logger.warning("token_failures 类型不支持 %s，设置为字典格式 {\"count\": 0}", type(token_failures))
                    normalised["token_failures"] = {"count": 0}

        # 添加调试日志：记录标准化后的状态字段变化
        if original_status != normalised.get("status"):
            logger.debug("状态字段标准化: %s -> %s", original_status, normalised.get("status"))
        if original_status_updated_at != normalised.get("status_updated_at"):
            logger.debug("状态更新时间标准化: %s -> %s", original_status_updated_at, normalised.get("status_updated_at"))
        if original_status_reason != normalised.get("status_reason"):
            logger.debug("状态原因标准化: %s -> %s", original_status_reason, normalised.get("status_reason"))
        if original_token_failures != normalised.get("token_failures"):
            new_token_failures = normalised.get("token_failures")
            if isinstance(new_token_failures, dict) and "count" in new_token_failures:
                logger.debug("令牌失败次数标准化: %s -> %s (count: %s)", original_token_failures, new_token_failures, new_token_failures.get("count"))
            else:
                logger.debug("令牌失败次数标准化: %s -> %s", original_token_failures, new_token_failures)

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

    def _has_critical_field_differences(self, email: str, local_payload: Dict[str, object], remote_payload: Dict[str, object]) -> bool:
        """检查关键字段是否有差异，即使校验和相同"""
        has_differences = False
        
        # 检查状态字段
        local_status = local_payload.get("status")
        remote_status = remote_payload.get("status")
        if local_status != remote_status:
            logger.debug("账户 %s 状态字段差异：本地=%s, 远程=%s", email, local_status, remote_status)
            has_differences = True
        
        # 检查状态更新时间字段
        local_status_updated = local_payload.get("status_updated_at")
        remote_status_updated = remote_payload.get("status_updated_at")
        if local_status_updated != remote_status_updated:
            logger.debug("账户 %s 状态更新时间差异：本地=%s, 远程=%s", email, local_status_updated, remote_status_updated)
            has_differences = True
        
        # 检查状态原因字段
        local_status_reason = local_payload.get("status_reason")
        remote_status_reason = remote_payload.get("status_reason")
        if local_status_reason != remote_status_reason:
            logger.debug("账户 %s 状态原因差异：本地=%s, 远程=%s", email, local_status_reason, remote_status_reason)
            has_differences = True
        
        # 检查令牌失败次数字段
        local_token_failures = local_payload.get("token_failures")
        remote_token_failures = remote_payload.get("token_failures")
        
        # token_failures 是字典类型，需要比较其中的 count 字段
        local_count = 0
        remote_count = 0
        
        # 提取本地的 count 值
        if isinstance(local_token_failures, dict) and "count" in local_token_failures:
            try:
                local_count = int(local_token_failures["count"]) if local_token_failures["count"] is not None else 0
            except (ValueError, TypeError):
                logger.debug("账户 %s 本地 token_failures.count 值无效: %s", email, local_token_failures["count"])
                local_count = 0
        elif isinstance(local_token_failures, (int, float, str)):
            try:
                local_count = int(local_token_failures) if local_token_failures is not None else 0
            except (ValueError, TypeError):
                logger.debug("账户 %s 本地 token_failures 值无效: %s", email, local_token_failures)
                local_count = 0
        
        # 提取远程的 count 值
        if isinstance(remote_token_failures, dict) and "count" in remote_token_failures:
            try:
                remote_count = int(remote_token_failures["count"]) if remote_token_failures["count"] is not None else 0
            except (ValueError, TypeError):
                logger.debug("账户 %s 远程 token_failures.count 值无效: %s", email, remote_token_failures["count"])
                remote_count = 0
        elif isinstance(remote_token_failures, (int, float, str)):
            try:
                remote_count = int(remote_token_failures) if remote_token_failures is not None else 0
            except (ValueError, TypeError):
                logger.debug("账户 %s 远程 token_failures 值无效: %s", email, remote_token_failures)
                remote_count = 0
        
        # 比较 count 值
        if local_count != remote_count:
            logger.debug("账户 %s 令牌失败次数差异：本地=%s, 远程=%s", email, local_count, remote_count)
            has_differences = True
        
        return has_differences

    @staticmethod
    def _log_async_result(future: Future) -> None:
        try:
            report = future.result()
            logger.info("后台同步完成：%s", report.message)
        except Exception as exc:  # noqa: BLE001
            logger.error("后台同步失败: %s", exc, exc_info=True)


__all__ = ["AccountSynchronizer", "SyncReport"]
