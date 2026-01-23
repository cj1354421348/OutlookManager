from __future__ import annotations

import json
import time
import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from typing import Dict, Tuple, Any, Optional

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
from app.core.time_utils import now_str, parse_iso
from datetime import timezone
from app.models.schemas import AccountSchema
from collections import defaultdict

_sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="accounts-sync")


def calculate_account_hash(data: Dict[str, Any]) -> str:
    """
    Calculate SHA256 hash of the account data, excluding volatile fields.
    """
    # Create a copy to avoid modifying original
    clean_data = data.copy()
    
    # Remove volatile fields that shoudn't affect the hash
    # status_updated_at might change on verify but business data is same
    # last_modified_at is what we are trying to fix/sync, so don't hash it
    volatile_fields = ["last_modified_at", "status_updated_at", "status_reason", "token_failures"]
    for field in volatile_fields:
        clean_data.pop(field, None)
        
    # Sort keys for consistent hashing
    canonical_json = json.dumps(clean_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()




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
        # Implement check-and-retry logic for robust connections (especially for Serverless DBs)
        max_retries = 3
        for attempt in range(max_retries):
            try:
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
            except psycopg2.OperationalError as e:
                if attempt == max_retries - 1:
                    logger.error("Failed to connect to database after %s attempts", max_retries)
                    raise
                
                wait_time = 1 * (attempt + 1)
                logger.warning("Database connection failed (attempt %s/%s): %s. Retrying in %ss...", 
                               attempt + 1, max_retries, e, wait_time)
                time.sleep(wait_time)

    def _ensure_schema(self, connection) -> None:
        """
        确保数据库表结构符合新的设计。
        如果不符合，直接删除重建（根据用户允许清空的指示）。
        """
        if self._schema_checked:
            return

        with connection.cursor() as cursor:
            # 检查主表是否存在
            cursor.execute(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'password'
                """,
                (self._table_name,),
            )
            has_new_schema = cursor.fetchone()

            # 再次检查是否还存在 content_hash 列 (如果存在说明不是最新 Schema)
            cursor.execute(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'content_hash'
                """,
                (self._table_name,),
            )
            has_content_hash = cursor.fetchone()

            if not has_new_schema or has_content_hash:
                logger.warning(f"表 {self._table_name} 结构不匹配（缺少 password 或 存在旧 content_hash），正在重建...")
                # 删除旧表
                cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}_tags CASCADE")
                cursor.execute(f"DROP TABLE IF EXISTS {self._table_name} CASCADE")
                # 删除关联的历史表(如果有)
                cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}_history CASCADE")

                # 创建新表
                cursor.execute(
                    f"""
                    CREATE TABLE {self._table_name} (
                        email VARCHAR(255) PRIMARY KEY,
                        password TEXT,       -- 独立存储密码
                        data TEXT NOT NULL,  -- JSON: {{"refresh_token": "...", "client_id": "..."}}
                        status VARCHAR(50) DEFAULT 'active',
                        status_updated_at TIMESTAMP WITH TIME ZONE,
                        status_reason TEXT,
                        token_failures TEXT, -- JSON Object
                        tags TEXT,           -- JSON Array
                        note TEXT,
                        last_modified_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        -- content_hash REMOVED
                        is_deleted BOOLEAN DEFAULT FALSE
                    )
                    """
                )
                connection.commit()
                logger.info(f"表 {self._table_name} 重建完成")

            # 检查并创建历史表 (无论主表是否重建，都检查历史表)
            cursor.execute(
                """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = %s
                """,
                (f"{self._table_name}_history",),
            )
            has_history_table = cursor.fetchone()

            if not has_history_table:
                logger.info(f"创建历史表 {self._table_name}_history...")
                cursor.execute(
                    f"""
                    CREATE TABLE {self._table_name}_history (
                        id SERIAL PRIMARY KEY,
                        original_email VARCHAR(255),
                        backup_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        backup_reason VARCHAR(50),
                        
                        password TEXT,
                        data TEXT,
                        status VARCHAR(50),
                        status_updated_at TIMESTAMP WITH TIME ZONE,
                        status_reason TEXT,
                        token_failures TEXT,
                        tags TEXT,
                        note TEXT,
                        last_modified_at TIMESTAMP WITH TIME ZONE,
                        -- content_hash REMOVED
                        is_deleted BOOLEAN
                    )
                    """
                )
                connection.commit()
            
            # 如果历史表存在，但包含 content_hash 列，也应该重建历史表以保持一致
            # 简单起见，这里依赖主表重建触发的级联删除，或者假设历史表结构随之更新。
            # 鉴于用户已允许数据变动，我们可以检查历史表是否有 content_hash，如果有则重建
            cursor.execute(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'content_hash'
                """,
                (f"{self._table_name}_history",),
            )
            has_history_hash = cursor.fetchone()
            if has_history_hash:
                 logger.warning(f"历史表 {self._table_name}_history 包含旧列 content_hash，重建中...")
                 cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}_history CASCADE")
                 cursor.execute(
                    f"""
                    CREATE TABLE {self._table_name}_history (
                        id SERIAL PRIMARY KEY,
                        original_email VARCHAR(255),
                        backup_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        backup_reason VARCHAR(50),
                        
                        password TEXT,
                        data TEXT,
                        status VARCHAR(50),
                        status_updated_at TIMESTAMP WITH TIME ZONE,
                        status_reason TEXT,
                        token_failures TEXT,
                        tags TEXT,
                        note TEXT,
                        last_modified_at TIMESTAMP WITH TIME ZONE,
                        is_deleted BOOLEAN
                    )
                    """
                )
                 connection.commit()

        self._schema_checked = True

    def enqueue_file_to_db(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto", file_mtime: float | None = None) -> Future | None:
        if not self.is_enabled:
            return None
        # Deepcopy to avoid concurrency issues during sync
        snapshot = json.loads(json.dumps(accounts))
        future = _sync_executor.submit(self.sync_file_to_db, snapshot, source=source, file_mtime=file_mtime)
        
        def _callback(fut):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Async sync failed: (See above for details)")
                # Exception is already logged in sync_file_to_db usually, or we can log here
                
        future.add_done_callback(_callback)
        return future

    def sync_file_to_db(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto", file_mtime: float | None = None) -> SyncReport:
        """
        PUSH: 将本地数据推送到数据库 (Force Sync + Backup)
        逻辑：实时计算Hash -> Hash 不同 -> 备份 DB 记录 -> 强制覆盖
        """
        if not self.is_enabled:
            raise RuntimeError("Database not configured")

        added = updated = skipped = removed = 0
        connection = self._connect()
        
        try:
            self._ensure_schema(connection)
            
            # 获取远程所有账户的完整信息 (用于计算实时 Hash)
            # 不再读取 content_hash 列
            remote_state = {}
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {self._table_name} WHERE is_deleted = FALSE")
                rows = cursor.fetchall()
                for row in rows:
                    # 实时计算远程数据的 Hash
                    remote_data = self._row_to_account_data(row)
                    remote_hash = calculate_account_hash(remote_data)
                    remote_state[row['email']] = remote_hash
            
            with connection.cursor() as cursor:
                for email, local_data in accounts.items():
                    local_hash = calculate_account_hash(local_data)
                    remote_hash = remote_state.get(email)

                    action = "skip"
                    should_push = False
                    
                    if email not in remote_state:
                         should_push = True
                         action = "insert"
                    elif local_hash != remote_hash:
                        # Hash 不一致，强制覆盖
                        should_push = True
                        action = "update"
                    
                    if should_push:
                        if action == "update":
                            # 更新前先备份 DB 中的旧数据
                            self._backup_db_record(cursor, email, f"overwrite_by_push_{source}")
                            # 清理旧备份 (保留 10 条)
                            self._cleanup_db_history(cursor, email)
                            updated += 1
                        else:
                            added += 1
                            
                        self._upsert_account(cursor, email, local_data)
                    else:
                        skipped += 1
            
            # --- Deletion Handling ---
            # Identify accounts present in DB but missing locally
            local_emails = set(accounts.keys())
            remote_emails = set(remote_state.keys())
            deleted_emails = remote_emails - local_emails
            
            if deleted_emails:
                with connection.cursor() as cursor:
                    for email in deleted_emails:
                        # Backup before soft delete
                        self._backup_db_record(cursor, email, f"deleted_by_push_{source}")
                        
                        cursor.execute(
                            f"UPDATE {self._table_name} SET is_deleted = TRUE, last_modified_at = %s WHERE email = %s",
                            (now_str(), email)
                        )
                        removed += 1
                        logger.info("Marked account %s as deleted in database.", email)
            
            connection.commit()
            
        except Exception as e:
            connection.rollback()
            logger.error(f"Sync file to db failed: {e}")
            raise
        finally:
            connection.close()

        msg = f"PUSH Sync: Added {added}, Updated {updated}, Skipped {skipped}, Removed {removed}"
        if added > 0 or updated > 0 or removed > 0:
            logger.info(msg)
        return SyncReport(message=msg, added=added, updated=updated, skipped=skipped, removed=removed)

    def _backup_db_record(self, cursor, email: str, reason: str) -> None:
        """
        将当前数据库记录备份到历史表
        """
        sql = f"""
        INSERT INTO {self._table_name}_history 
        (original_email, backup_reason, password, data, status, status_updated_at, status_reason, token_failures, tags, note, last_modified_at, is_deleted)
        SELECT 
            email, %s, password, data, status, status_updated_at, status_reason, token_failures, tags, note, last_modified_at, is_deleted
        FROM {self._table_name}
        WHERE email = %s
        """
        cursor.execute(sql, (reason, email))

    def _cleanup_db_history(self, cursor, email: str) -> None:
        """
        清理历史表，只保留最近 10 条
        """
        sql = f"""
        DELETE FROM {self._table_name}_history 
        WHERE original_email = %s 
        AND id NOT IN (
            SELECT id FROM {self._table_name}_history 
            WHERE original_email = %s 
            ORDER BY backup_timestamp DESC 
            LIMIT 10
        )
        """
        cursor.execute(sql, (email, email))

    def sync_db_to_file(self, local_accounts: Dict[str, Dict[str, object]]) -> Tuple[Dict[str, Dict[str, object]], SyncReport, bool]:
        """
        PULL: 将数据库中的数据拉取到本地 (Force Sync + Backup)
        逻辑：实时计算Hash -> Hash 不同 -> 备份本地文件 -> 强制覆盖
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
                
                # 实时计算远程 Hash
                remote_data = self._row_to_account_data(row)
                remote_hash = calculate_account_hash(remote_data)
                
                local_data = merged_accounts.get(email)
                local_hash = calculate_account_hash(local_data) if local_data else None

                should_pull = False
                action = "skip"

                if email not in merged_accounts:
                    should_pull = True
                    action = "insert"
                elif local_hash != remote_hash:
                     # Hash 不一致，强制从服务器拉取覆盖本地
                     should_pull = True
                     action = "update"
                
                if should_pull:
                    if action == "update":
                        # 覆盖前备份本地数据
                        self._backup_local_record(email, local_data)
                        self._cleanup_local_backups(email)
                        updated += 1
                    else:
                        added += 1

                    merged_accounts[email] = remote_data
                    has_changes = True
                else:
                    skipped += 1
        
        except Exception as e:
            logger.error(f"Sync db to file failed: {e}")
            raise
        finally:
            connection.close()
            
        msg = f"PULL Sync: Added {added}, Updated {updated}, Skipped {skipped}"
        if has_changes:
            logger.info(msg)
            
        return merged_accounts, SyncReport(message=msg, added=added, updated=updated, skipped=skipped), has_changes

    def _backup_local_record(self, email: str, data: Dict[str, Any]) -> None:
        """
        将本地单个账号数据备份为独立 JSON 文件
        目录：{BASE_DIR}/data/backups/
        文件名：{email}_{timestamp}.json
        """
        try:
            from app.config import BASE_DIR
            backup_dir = BASE_DIR / "data" / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            ts_str = int(time.time())
            # 文件名处理安全字符，邮箱中的特殊符号
            safe_email = email.replace("/", "_").replace("\\", "_")
            filename = f"{safe_email}_{ts_str}.json"
            
            file_path = backup_dir / filename
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Backed up local data for {email} to {file_path}")
        except Exception as e:
            logger.error(f"Failed to backup local record for {email}: {e}")

    def _cleanup_local_backups(self, email: str) -> None:
        """
        清理本地备份，只保留最近 10 个
        """
        try:
            from app.config import BASE_DIR
            backup_dir = BASE_DIR / "data" / "backups"
            if not backup_dir.exists():
                return
            
            # 安全文件名匹配
            safe_email = email.replace("/", "_").replace("\\", "_")
            pattern = f"{safe_email}_*.json"
            
            files = list(backup_dir.glob(pattern))
            
            if len(files) <= 10:
                return
                
            # 按修改时间倒序（最新的在前）
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            # 删除第 10 个以后的
            to_delete = files[10:]
            for f in to_delete:
                with suppress(Exception):
                    f.unlink()
            
            if to_delete:
                logger.debug(f"Cleaned up {len(to_delete)} old backups for {email}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup local backups for {email}: {e}")

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
        password = data.get("password")
        
        # auth_data excludes password now
        auth_data = {
            "refresh_token": data.get("refresh_token"),
            "client_id": data.get("client_id"),
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
        (email, password, data, status, status_updated_at, status_reason, token_failures, tags, note, last_modified_at, is_deleted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
        ON CONFLICT (email) DO UPDATE SET
            password = EXCLUDED.password,
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
            password,
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
            
        # 2. Add password from column
        data['password'] = row.get('password')

        # 3. Mix in other fields
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
            data['last_modified_at'] = dt.astimezone().isoformat()
            
        if row['status_updated_at']:
             dt = row['status_updated_at']
             if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
             data['status_updated_at'] = dt.astimezone().isoformat()
            
        # 补全可能缺失的字段以匹配 Schema (Optional)
        return data
