from __future__ import annotations

import json
import re
import threading
from hashlib import sha256
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import (
    ACCOUNTS_DB_HOST,
    ACCOUNTS_DB_NAME,
    ACCOUNTS_DB_PASSWORD,
    ACCOUNTS_DB_PORT,
    ACCOUNTS_DB_USER,
    DATABASE_URL,
    EMAIL_DETAIL_CACHE_TABLE,
    EMAIL_LIST_CACHE_TABLE,
    logger,
)
from app.models import EmailDetailsResponse, EmailItem, EmailListResponse


class _BaseCacheRepository:
    _TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

    def __init__(self, table_name: str | None, default_name: str) -> None:
        self._table_name = self._normalise_table_name(table_name, default_name)
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    @property
    def is_enabled(self) -> bool:
        if DATABASE_URL:
            return True
        return all([ACCOUNTS_DB_HOST, ACCOUNTS_DB_USER, ACCOUNTS_DB_PASSWORD, ACCOUNTS_DB_NAME])

    def _ensure_schema(self, connection: "psycopg2.extensions.connection") -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with connection.cursor() as cursor:
                self._create_schema(cursor)
            connection.commit()
            self._schema_ready = True

    def _connect(self) -> "psycopg2.extensions.connection":
        if DATABASE_URL:
            return psycopg2.connect(DATABASE_URL, sslmode="require")
        return psycopg2.connect(
            host=ACCOUNTS_DB_HOST,
            port=ACCOUNTS_DB_PORT,
            user=ACCOUNTS_DB_USER,
            password=ACCOUNTS_DB_PASSWORD,
            database=ACCOUNTS_DB_NAME,
            sslmode="require",
        )

    def _normalise_table_name(self, name: str | None, default: str) -> str:
        if name and self._TABLE_NAME_PATTERN.match(name):
            return name
        if name:
            logger.warning("非法的缓存表名 %s，已回退为 %s", name, default)
        return default

    def _create_schema(self, cursor: "psycopg2.extensions.cursor") -> None:
        raise NotImplementedError


class EmailListCacheRepository(_BaseCacheRepository):
    def __init__(self) -> None:
        super().__init__(EMAIL_LIST_CACHE_TABLE, "email_list_cache")

    def save(
        self,
        email_id: str,
        folder: str,
        page: int,
        page_size: int,
        emails: list[EmailItem],
        total_emails: int,
    ) -> None:
        if not self.is_enabled:
            return

        if any(item.uid in (None, "") for item in emails):
            logger.debug("Skip list cache for %s %s:%s because of missing UID", email_id, folder, page)
            return

        payload = {
            "emails": [item.model_dump() for item in emails],
        }
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        checksum = sha256(payload_json.encode("utf-8")).hexdigest()

        try:
            connection = self._connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to connect to list cache when storing %s: %s", email_id, exc)
            return

        try:
            self._ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO "{self._table_name}" (email_id, folder, page, page_size, total_emails, payload, checksum, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (email_id, folder, page, page_size)
                    DO UPDATE SET
                        total_emails = EXCLUDED.total_emails,
                        payload = EXCLUDED.payload,
                        checksum = EXCLUDED.checksum,
                        synced_at = CURRENT_TIMESTAMP
                    """,
                    (email_id, folder, page, page_size, total_emails, payload_json, checksum),
                )
            connection.commit()
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            logger.warning("Failed to persist list cache for %s %s:%s: %s", email_id, folder, page, exc)
        finally:
            connection.close()

    def load(
        self,
        email_id: str,
        folder: str,
        page: int,
        page_size: int,
    ) -> Optional[EmailListResponse]:
        if not self.is_enabled:
            return None

        try:
            connection = self._connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to connect to list cache when reading %s: %s", email_id, exc)
            return None

        try:
            self._ensure_schema(connection)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
                    SELECT total_emails, payload
                    FROM "{self._table_name}"
                    WHERE email_id = %s AND folder = %s AND page = %s AND page_size = %s
                    """,
                    (email_id, folder, page, page_size),
                )
                row = cursor.fetchone()
            connection.commit()
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            logger.warning("Failed to read list cache for %s %s:%s: %s", email_id, folder, page, exc)
            return None
        finally:
            connection.close()

        if not row or not row.get("payload"):
            return None

        try:
            payload = json.loads(row["payload"])
            emails = [EmailItem.model_validate(item) for item in payload.get("emails", [])]
            response = EmailListResponse(
                email_id=email_id,
                folder_view=folder,
                page=page,
                page_size=page_size,
                total_emails=int(row.get("total_emails", 0)),
                emails=emails,
                from_cache=True,
            )
            return response
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse list cache payload for %s %s:%s: %s", email_id, folder, page, exc)
            return None

    def _create_schema(self, cursor: "psycopg2.extensions.cursor") -> None:  # noqa: D401
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self._table_name}" (
                email_id VARCHAR(255) NOT NULL,
                folder VARCHAR(64) NOT NULL,
                page INTEGER NOT NULL,
                page_size INTEGER NOT NULL,
                total_emails INTEGER NOT NULL,
                payload TEXT NOT NULL,
                checksum CHAR(64) NOT NULL,
                synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (email_id, folder, page, page_size)
            )
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self._table_name}_email_folder"
            ON "{self._table_name}" (email_id, folder)
            """
        )


class CachedEmailDetail:
    __slots__ = ("response", "folder", "uid")

    def __init__(self, response: EmailDetailsResponse | None, folder: str | None, uid: str | None) -> None:
        self.response = response
        self.folder = folder
        self.uid = uid


class EmailDetailCacheRepository(_BaseCacheRepository):
    def __init__(self) -> None:
        super().__init__(EMAIL_DETAIL_CACHE_TABLE, "email_detail_cache")

    def register_stub(self, email_id: str, message_id: str, folder: str, uid: str | None) -> None:
        if not self.is_enabled or not uid:
            return
        self._write_record(email_id, message_id, folder, uid, payload=None, checksum=None)

    def save_detail(
        self,
        email_id: str,
        message_id: str,
        folder: str,
        uid: str | None,
        detail: EmailDetailsResponse,
    ) -> None:
        if not self.is_enabled:
            return
        if not uid:
            logger.debug("Skip detail cache for %s %s because UID missing", email_id, message_id)
            return
        payload_json = json.dumps(detail.model_dump(), ensure_ascii=False, sort_keys=True)
        checksum = sha256(payload_json.encode("utf-8")).hexdigest()
        self._write_record(email_id, message_id, folder, uid, payload=payload_json, checksum=checksum)

    def load(self, email_id: str, message_id: str) -> CachedEmailDetail | None:
        return self._read_record(email_id=email_id, message_id=message_id, uid=None, folder=None)

    def load_by_uid(self, email_id: str, folder: str, uid: str) -> CachedEmailDetail | None:
        return self._read_record(email_id=email_id, message_id=None, uid=uid, folder=folder)

    def _write_record(
        self,
        email_id: str,
        message_id: str,
        folder: str,
        uid: str | None,
        payload: str | None,
        checksum: str | None,
    ) -> None:
        try:
            connection = self._connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to connect to detail cache when storing %s: %s", email_id, exc)
            return

        try:
            self._ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO "{self._table_name}" (email_id, message_id, folder, uid, payload, checksum, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (email_id, message_id)
                    DO UPDATE SET
                        folder = EXCLUDED.folder,
                        uid = COALESCE(EXCLUDED.uid, "{self._table_name}"."uid"),
                        payload = COALESCE(EXCLUDED.payload, "{self._table_name}"."payload"),
                        checksum = COALESCE(EXCLUDED.checksum, "{self._table_name}"."checksum"),
                        synced_at = CURRENT_TIMESTAMP
                    """,
                    (email_id, message_id, folder, uid, payload, checksum),
                )
            connection.commit()
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            logger.warning("Failed to persist detail cache for %s %s: %s", email_id, message_id, exc)
        finally:
            connection.close()

    def _read_record(
        self,
        *,
        email_id: str,
        message_id: str | None,
        uid: str | None,
        folder: str | None,
    ) -> CachedEmailDetail | None:
        try:
            connection = self._connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to connect to detail cache when reading %s: %s", email_id, exc)
            return None

        try:
            self._ensure_schema(connection)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                if message_id is not None:
                    cursor.execute(
                        f"""
                        SELECT folder, uid, payload
                        FROM "{self._table_name}"
                        WHERE email_id = %s AND message_id = %s
                        """,
                        (email_id, message_id),
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT folder, uid, payload
                        FROM "{self._table_name}"
                        WHERE email_id = %s AND folder = %s AND uid = %s
                        """,
                        (email_id, folder, uid),
                    )
                row = cursor.fetchone()
            connection.commit()
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            logger.warning("Failed to read detail cache for %s: %s", email_id, exc)
            return None
        finally:
            connection.close()

        if not row:
            return None

        response: EmailDetailsResponse | None = None
        payload = row.get("payload")
        if payload:
            try:
                response = EmailDetailsResponse.model_validate_json(payload)
                response.from_cache = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse detail cache payload for %s: %s", email_id, exc)
                response = None

        return CachedEmailDetail(response=response, folder=row.get("folder"), uid=row.get("uid"))

    def _create_schema(self, cursor: "psycopg2.extensions.cursor") -> None:  # noqa: D401
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self._table_name}" (
                email_id VARCHAR(255) NOT NULL,
                message_id VARCHAR(255) NOT NULL,
                folder VARCHAR(64) NOT NULL,
                uid VARCHAR(128),
                payload TEXT,
                checksum CHAR(64),
                synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (email_id, message_id)
            )
            """
        )
        cursor.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS "idx_{self._table_name}_uid"
            ON "{self._table_name}" (email_id, folder, uid)
            WHERE uid IS NOT NULL
            """
        )


email_list_cache_repository = EmailListCacheRepository()
email_detail_cache_repository = EmailDetailCacheRepository()

__all__ = [
    "EmailListCacheRepository",
    "EmailDetailCacheRepository",
    "CachedEmailDetail",
    "email_list_cache_repository",
    "email_detail_cache_repository",
]
