from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi

from app.config import (
    ACCOUNTS_SYNC_POLICY,
    MONGO_ACCOUNTS_COLLECTION,
    MONGO_DB_NAME,
    MONGO_URI,
    logger,
)

SYNC_ENABLED = bool(MONGO_URI)
TIMESTAMP_FIELD = "updated_at"


class MongoSyncError(Exception):
    """Raised when MongoDB synchronization fails."""


@dataclass
class SyncStats:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "conflicts": self.conflicts,
        }


_client_lock = threading.Lock()
_client: MongoClient | None = None


def _get_collection() -> Collection | None:
    if not SYNC_ENABLED:
        return None

    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                try:
                    _client = MongoClient(MONGO_URI, server_api=ServerApi("1"))
                except PyMongoError as exc:
                    logger.error("Failed to initialize MongoDB client: %s", exc)
                    raise MongoSyncError("MongoDB connection failed") from exc

    try:
        client = _client  # type: ignore[assignment]
        if client is None:
            return None
        client.admin.command("ping")
        return client[MONGO_DB_NAME][MONGO_ACCOUNTS_COLLECTION]
    except PyMongoError as exc:
        logger.error("MongoDB ping failed: %s", exc)
        raise MongoSyncError("MongoDB ping failed") from exc


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _ensure_timestamp(data: Dict[str, Any]) -> datetime:
    existing = _parse_timestamp(data.get(TIMESTAMP_FIELD))
    if existing is not None:
        data[TIMESTAMP_FIELD] = existing.astimezone(timezone.utc).isoformat()
        return existing.astimezone(timezone.utc)

    stamp = _now()
    data[TIMESTAMP_FIELD] = stamp.isoformat()
    return stamp


def _prepare_remote_doc(email: str, data: Dict[str, Any]) -> Dict[str, Any]:
    doc = {key: value for key, value in data.items() if key != "_id"}
    doc["email"] = email
    _ensure_timestamp(doc)
    return doc


def _strip_for_local(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {key: value for key, value in data.items() if key != "email"}
    return cleaned


def sync_accounts_to_mongo(local_accounts: Dict[str, Dict[str, Any]]) -> SyncStats:
    if not SYNC_ENABLED:
        return SyncStats()

    collection = _get_collection()
    if collection is None:
        return SyncStats()

    stats = SyncStats()

    try:
        remote_docs = {
            doc["email"]: doc
            for doc in collection.find({}, {"_id": 0})
            if "email" in doc
        }

        for email, payload in local_accounts.items():
            local_data = dict(payload)
            local_ts = _ensure_timestamp(local_data)
            remote_doc = remote_docs.pop(email, None)

            if remote_doc is None:
                collection.update_one({"email": email}, {"$set": _prepare_remote_doc(email, local_data)}, upsert=True)
                stats.inserted += 1
                continue

            remote_ts = _parse_timestamp(remote_doc.get(TIMESTAMP_FIELD))
            if remote_ts and remote_ts > local_ts and ACCOUNTS_SYNC_POLICY == "remote":
                stats.skipped += 1
                stats.conflicts.append(email)
                continue

            collection.update_one({"email": email}, {"$set": _prepare_remote_doc(email, local_data)}, upsert=True)
            stats.updated += 1

        for email in remote_docs:
            if ACCOUNTS_SYNC_POLICY == "remote":
                stats.skipped += 1
                stats.conflicts.append(email)
                continue
            collection.delete_one({"email": email})
            stats.deleted += 1

        return stats
    except PyMongoError as exc:
        logger.error("Failed to sync accounts to MongoDB: %s", exc)
        raise MongoSyncError("Sync to MongoDB failed") from exc


def merge_remote_into_local(local_accounts: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], SyncStats]:
    if not SYNC_ENABLED:
        return dict(local_accounts), SyncStats()

    collection = _get_collection()
    if collection is None:
        return dict(local_accounts), SyncStats()

    stats = SyncStats()
    merged: Dict[str, Dict[str, Any]] = {}
    for email, data in local_accounts.items():
        local_copy = dict(data)
        _ensure_timestamp(local_copy)
        merged[email] = local_copy

    try:
        remote_docs = list(collection.find({}, {"_id": 0}))
    except PyMongoError as exc:
        logger.error("Failed to fetch accounts from MongoDB: %s", exc)
        raise MongoSyncError("Fetch from MongoDB failed") from exc

    remote_index = {doc.get("email"): dict(doc) for doc in remote_docs if doc.get("email")}

    for email, doc in remote_index.items():
        remote_data = dict(doc)
        remote_ts = _ensure_timestamp(remote_data)

        local_data = merged.get(email)
        if local_data is None:
            merged[email] = _strip_for_local(remote_data)
            stats.inserted += 1
            continue

        local_ts = _parse_timestamp(local_data.get(TIMESTAMP_FIELD))
        if local_ts is None:
            merged[email] = _strip_for_local(remote_data)
            stats.updated += 1
            continue

        if remote_ts and local_ts and remote_ts > local_ts:
            merged[email] = _strip_for_local(remote_data)
            stats.updated += 1
            stats.conflicts.append(email)
            continue

        if ACCOUNTS_SYNC_POLICY == "remote":
            merged[email] = _strip_for_local(remote_data)
            stats.updated += 1
            stats.conflicts.append(email)
            continue

        stats.skipped += 1

    remote_emails = set(remote_index.keys())

    for email in list(merged.keys()):
        if email in remote_emails:
            continue
        if ACCOUNTS_SYNC_POLICY == "remote":
            merged.pop(email, None)
            stats.deleted += 1
            stats.conflicts.append(email)

    return merged, stats


__all__ = [
    "MongoSyncError",
    "SyncStats",
    "merge_remote_into_local",
    "sync_accounts_to_mongo",
]
