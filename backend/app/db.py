"""Async MongoDB access.

pymongo >= 4.10 ships AsyncMongoClient natively; motor is deprecated and its EOL
has passed, so it is deliberately not used here.
"""

from __future__ import annotations

import numpy as np
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings, get_settings
from app.security import crypto, rotation

_client: AsyncMongoClient | None = None
_db: AsyncDatabase | None = None

# Loaded once at startup and held in process memory, never in MongoDB.
_kek: bytes | None = None
_rotation: np.ndarray | None = None


async def connect(settings: Settings | None = None) -> AsyncDatabase:
    global _client, _db, _kek, _rotation
    settings = settings or get_settings()

    _client = AsyncMongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    await _client.admin.command("ping")
    _db = _client[settings.mongo_db]

    _kek = crypto.load_kek(settings.kek_file)
    _rotation = rotation.load_rotation(settings.rotation_file)
    return _db


async def disconnect() -> None:
    global _client, _db, _kek, _rotation
    if _client is not None:
        await _client.close()
    _client, _db = None, None
    # Drop key material on shutdown rather than leaving it in a module global.
    _kek, _rotation = None, None


def get_db() -> AsyncDatabase:
    if _db is None:
        raise RuntimeError("Database not connected. connect() runs in the app lifespan.")
    return _db


def get_kek() -> bytes:
    if _kek is None:
        raise RuntimeError("KEK not loaded. Run scripts/gen_keys.py.")
    return _kek


def get_rotation() -> np.ndarray:
    if _rotation is None:
        raise RuntimeError("Rotation matrix not loaded. Run scripts/gen_keys.py.")
    return _rotation


def is_connected() -> bool:
    return _db is not None
