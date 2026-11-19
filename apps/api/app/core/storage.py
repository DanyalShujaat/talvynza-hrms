"""Private file storage. Files are never served from a public URL: downloads go through an authorized endpoint.

LocalStorage is the default adapter. An S3-compatible adapter implements the same three methods.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import ValidationFailed

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {
    "application/pdf", "image/png", "image/jpeg", "text/plain", "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Malware scanning hook. Deployments register a scanner (for example ClamAV) that raises on a hit.
_scanners: list[Callable[[bytes, str], None]] = []


def register_scanner(fn: Callable[[bytes, str], None]) -> None:
    _scanners.append(fn)


def validate_upload(data: bytes, filename: str, content_type: str) -> None:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationFailed("File is larger than 10 MB", code="file_too_large")
    if not data:
        raise ValidationFailed("File is empty", code="empty_file")
    if content_type not in ALLOWED_TYPES:
        raise ValidationFailed("File type is not allowed", code="file_type_not_allowed")
    for scan in _scanners:
        scan(data, filename)


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, tenant_id: uuid.UUID, data: bytes) -> str:
        key = f"{tenant_id}/{uuid.uuid4().hex}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)
