"""Tiny sqlite key/value cache with per-read TTL."""
import json
import os
import sqlite3
import time
from pathlib import Path

_db = sqlite3.connect(os.getenv("CACHE_DB") or Path(__file__).parent.parent / "cache.sqlite3", check_same_thread=False)
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, t REAL)")


def get(key: str, ttl: float):
    row = _db.execute("SELECT v, t FROM kv WHERE k = ?", (key,)).fetchone()
    if row and time.time() - row[1] < ttl:
        return json.loads(row[0])
    return None


def set(key: str, value) -> None:
    _db.execute("REPLACE INTO kv VALUES (?, ?, ?)", (key, json.dumps(value), time.time()))
    _db.commit()


def drop_prefix(prefix: str) -> None:
    _db.execute("DELETE FROM kv WHERE k LIKE ?", (prefix + "%",))
    _db.commit()
