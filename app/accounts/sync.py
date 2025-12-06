from __future__ import annotations

import json
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from typing import Dict, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import (
    ACCOUNTS_DB_HOST,
    ACCOUNTS_DB_NAME,
    ACCOUNTS_DB_PASSWORD,
    ACCOUNTS_DB_PORT,
    ACCOUNTS_DB_TABLE,
    ACCOUNTS_DB_USER,
    DATABASE_URL,
    logger,
)
from app.core.time_utils import now_str, parse_iso, TIMEZONE_SHANGHAI
from datetime import timezone
from app.models.schemas import AccountSchema
from collections import defaultdict

_sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="accounts-sync")


@dataclass(slots=True)
class SyncReport:
    message: str
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0

    def to_dict(self) -> Dict[str, int | str]:
        return {
            "message": self.message,
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "skipped": self.skipped,
        }


class AccountSynchronizer:
    def __init__(self) -> None:
        self._table_name = ACCOUNTS_DB_TABLE or "account_backups"
        self._schema_checked = False

    @property
    def is_enabled(self) -> bool:
        if DATABASE_URL:
            return True
        return all([ACCOUNTS_DB_HOST, ACCOUNTS_DB_USER, ACCOUNTS_DB_PASSWORD, ACCOUNTS_DB_NAME])

    def _connect(self):
        if DATABASE_URL:
            return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return psycopg2.connect(
            host=ACCOUNTS_DB_HOST,
            user=ACCOUNTS_DB_USER,
            password=ACCOUNTS_DB_PASSWORD,
            dbname=ACCOUNTS_DB_NAME,
            port=ACCOUNTS_DB_PORT,
            cursor_factory=RealDictCursor,
        )

    def _ensure_schema(self, connection) -> None:
        """
        确保数据库表结构符合新的设计。
        如果不符合，直接删除重建（根据用户允许清空的指示）。
        """
        if self._schema_checked:
            return

        with connection.cursor() as cursor:
            # 检查表是否存在以及是否包含新字段 last_modified_at
            cursor.execute(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'last_modified_at'
                """,
                (self._table_name,),
            )
            has_new_schema = cursor.fetchone()

            if not has_new_schema:
                logger.warning(f"表 {self._table_name} 结构不匹配或不存在，正在重建...")
                # 删除旧表和关联表（如果存在）
                cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}_tags CASCADE")
                cursor.execute(f"DROP TABLE IF EXISTS {self._table_name} CASCADE")

                # 创建新表
                # data 字段只存 refresh_token 和 client_id
                cursor.execute(
                    f"""
                    CREATE TABLE {self._table_name} (
                        email VARCHAR(255) PRIMARY KEY,
                        data TEXT NOT NULL,  -- JSON: {{"refresh_token": "...", "client_id": "..."}}
                        status VARCHAR(50) DEFAULT 'active',
                        status_updated_at TIMESTAMP WITH TIME ZONE,
                        status_reason TEXT,
                        token_failures TEXT, -- JSON Object
                        tags TEXT,           -- JSON Array
                        note TEXT,
                        last_modified_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        is_deleted BOOLEAN DEFAULT FALSE
                    )
                    """
                )
                connection.commit()
                logger.info(f"表 {self._table_name} 重建完成")
            
        self._schema_checked = True

    def enqueue_file_to_db(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto") -> Future | None:
        if not self.is_enabled:
            return None
        # Deepcopy to avoid concurrency issues during sync
        snapshot = json.loads(json.dumps(accounts))
        future = _sync_executor.submit(self.sync_file_to_db, snapshot, source=source)
        
        def _callback(fut):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Async sync failed: {e}", exc_info=True)
                
        future.add_done_callback(_callback)
        return future

    def sync_file_to_db(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto") -> SyncReport:
        """
        PUSH: 将本地更有新意的数据推送到数据库
        """
        if not self.is_enabled:
            raise RuntimeError("Database not configured")

        added = updated = skipped = 0
        connection = self._connect()
        
        try:
            self._ensure_schema(connection)
            
            # 获取远程所有账户的时间戳
            remote_state = {}
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT email, last_modified_at FROM {self._table_name}")
                rows = cursor.fetchall()
                for row in rows:
                    if row['last_modified_at']:
                        # 强制使用东八区格式化，确比较的一致性
                        dt = row['last_modified_at']
                        if dt.tzinfo is None:
                            # 假设 UTC 如果没有时区
                            dt = dt.replace(tzinfo=timezone.utc)
                        # 统一转为东八区
                        remote_state[row['email']] = dt.astimezone(TIMEZONE_SHANGHAI).isoformat()
            
            with connection.cursor() as cursor:
                for email, local_data in accounts.items():
                    local_ts_str = local_data.get("last_modified_at")
                    remote_ts_str = remote_state.get(email)

                    # 决定是否更新：
                    # 1. 远程不存在 -> 插入
                    # 2. 远程存在，但 Local 更面 -> 更新
                    
                    should_push = False
                    if email not in remote_state:
                        should_push = True
                        action = "insert"
                    elif self._is_newer(local_ts_str, remote_ts_str):
                        should_push = True
                        action = "update"
                    else:
                        skipped += 1
                        continue

                    if should_push:
                        logger.debug("PUSH %s: Local (%s) > Remote (%s)", email, local_ts_str, remote_ts_str)
                        self._upsert_account(cursor, email, local_data)
                        if action == "insert":
                            added += 1
                        else:
                            updated += 1
                    else:
                        logger.debug("SKIP %s: Local (%s) <= Remote (%s)", email, local_ts_str, remote_ts_str)
                        skipped += 1
            
            connection.commit()
            
        except Exception as e:
            connection.rollback()
            logger.error(f"Sync file to db failed: {e}")
            raise
        finally:
            connection.close()

        msg = f"PUSH Sync: Added {added}, Updated {updated}, Skipped {skipped}"
        logger.info(msg)
        return SyncReport(message=msg, added=added, updated=updated, skipped=skipped)

    def sync_db_to_file(self, local_accounts: Dict[str, Dict[str, object]]) -> Tuple[Dict[str, Dict[str, object]], SyncReport, bool]:
        """
        PULL: 将数据库中更有新意的数据拉取到本地
        """
        if not self.is_enabled:
             raise RuntimeError("Database not configured")

        connection = self._connect()
        merged_accounts = local_accounts.copy()
        updated = added = skipped = 0
        has_changes = False

        try:
            self._ensure_schema(connection)

            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {self._table_name} WHERE is_deleted = FALSE")
                remote_rows = cursor.fetchall()

            for row in remote_rows:
                email = row['email']
                remote_ts = row['last_modified_at'].isoformat() if row['last_modified_at'] else None
                
                local_data = merged_accounts.get(email)
                local_ts = local_data.get("last_modified_at") if local_data else None

                # 决定是否拉取：
                # 1. 本地不存在 -> 拉取
                # 2. 本地存在，但 Remote 更面 -> 拉取
                
                if email not in merged_accounts:
                    # New account from DB
                    merged_accounts[email] = self._row_to_account_data(row)
                    added += 1
                    has_changes = True
                elif self._is_newer(remote_ts, local_ts):
                    # Remote is newer
                    merged_accounts[email] = self._row_to_account_data(row)
                    updated += 1
                    has_changes = True
                else:
                    skipped += 1
        
        finally:
            connection.close()
            
        msg = f"PULL Sync: Added {added}, Updated {updated}, Skipped {skipped}"
        if has_changes:
            logger.info(msg)
            
        return merged_accounts, SyncReport(message=msg, added=added, updated=updated, skipped=skipped), has_changes

    def _is_newer(self, ts1_str: str | None, ts2_str: str | None) -> bool:
        """
        Returns True if ts1 > ts2
        If ts1 is None, it is NEVER newer (unless ts2 is also None, then False).
        If ts2 is None, ts1 (if exists) IS newer.
        """
        if not ts1_str:
            return False
        if not ts2_str:
            return True
        
        try:
            dt1 = parse_iso(ts1_str)
            dt2 = parse_iso(ts2_str)
            return dt1 > dt2
        except Exception:
            logger.warning(f"Error comparing timestamps: {ts1_str} vs {ts2_str}")
            return False

    def _upsert_account(self, cursor, email: str, data: Dict[str, Any]):
        """
        Insert or Update account in DB decomposing the JSON data
        """
        # Prepare parts
        auth_data = {
            "refresh_token": data.get("refresh_token"),
            "client_id": data.get("client_id")
        }
        
        status = data.get("status", "active")
        status_updated_at = data.get("status_updated_at")
        status_reason = data.get("status_reason")
        
        token_failures = data.get("token_failures")
        token_failures_json = json.dumps(token_failures) if token_failures else None
        
        tags = data.get("tags", [])
        tags_json = json.dumps(tags)
        
        note = data.get("note")
        
        # Ensure we have a timestamp for DB
        last_modified_at = data.get("last_modified_at") or now_str()

        sql = f"""
        INSERT INTO {self._table_name} 
        (email, data, status, status_updated_at, status_reason, token_failures, tags, note, last_modified_at, is_deleted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
        ON CONFLICT (email) DO UPDATE SET
            data = EXCLUDED.data,
            status = EXCLUDED.status,
            status_updated_at = EXCLUDED.status_updated_at,
            status_reason = EXCLUDED.status_reason,
            token_failures = EXCLUDED.token_failures,
            tags = EXCLUDED.tags,
            note = EXCLUDED.note,
            last_modified_at = EXCLUDED.last_modified_at,
            is_deleted = FALSE
        """
        
        cursor.execute(sql, (
            email,
            json.dumps(auth_data),
            status,
            status_updated_at,
            status_reason,
            token_failures_json,
            tags_json,
            note,
            last_modified_at
        ))

    def _row_to_account_data(self, row: dict) -> Dict[str, Any]:
        """
        Reconstruct the full account JSON from DB row
        """
        # 1. Base auth data
        try:
            data = json.loads(row['data'])
        except Exception:
            data = {}
            
        # 2. Mix in other fields
        data['status'] = row['status']
        if row['status_updated_at']:
             data['status_updated_at'] = row['status_updated_at'].isoformat()
        
        if row['status_reason']:
            data['status_reason'] = row['status_reason']
            
        if row['token_failures']:
            try:
                data['token_failures'] = json.loads(row['token_failures'])
            except:
                pass
                
        if row['tags']:
            try:
                data['tags'] = json.loads(row['tags'])
            except:
                data['tags'] = []
        else:
            data['tags'] = []
            
        if row['note']:
            data['note'] = row['note']
            
        if row['last_modified_at']:
            # 强制转换为东八区 ISO 字符串
            dt = row['last_modified_at']
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            data['last_modified_at'] = dt.astimezone(TIMEZONE_SHANGHAI).isoformat()
            
        if row['status_updated_at']:
             dt = row['status_updated_at']
             if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
             data['status_updated_at'] = dt.astimezone(TIMEZONE_SHANGHAI).isoformat()
            
        # 补全可能缺失的字段以匹配 Schema (Optional)
        return data
