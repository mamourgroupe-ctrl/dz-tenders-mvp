"""Upload validation and storage for payment proofs.

Defence in depth, not a filename check:

1. size limit (``APP_MAX_UPLOAD_BYTES``, 5 MiB by default);
2. magic-byte sniffing for PDF, JPEG and PNG — the declared MIME type and the
   extension are ignored when they disagree;
3. random server-side name inside ``APP_UPLOAD_DIR``; the client name is kept
   only as metadata, stripped of path separators;
4. SHA-256 recorded so duplicate proofs can be detected later.

Files are written with explicit permissions and never executed: the web app
serves them only from the dedicated payment-proof route, not from ``/static``.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from webapp.config import Settings

#: ``request`` content types accepted for proofs.
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

#: (prefix, canonical MIME, extension) checked against the file bytes.
_MAGIC = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)

_UNSAFE = re.compile(r"[\\/\x00-\x1f]")


class UploadError(Exception):
    """A rejected upload with an Arabic user-facing message."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class StoredFile:
    """Metadata of a validated file written to disk."""

    stored_name: str
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str


def sniff_content_type(data: bytes) -> tuple[str, str] | None:
    """Return ``(mime, extension)`` from magic bytes, or ``None``."""
    for prefix, mime, extension in _MAGIC:
        if data.startswith(prefix):
            return mime, extension
    return None


def clean_original_name(name: str) -> str:
    """Strip directories and control characters from a client filename."""
    cleaned = _UNSAFE.sub("_", name or "proof").strip("._ ")
    return cleaned[:180] or "proof"


def validate_upload(
    data: bytes, *, original_name: str, declared_type: str, max_bytes: int
) -> tuple[str, str]:
    """Validate an uploaded proof and return ``(mime, extension)``.

    Raises:
        UploadError: empty file, too large, or unsupported/inconsistent type.
    """
    if not data:
        raise UploadError("الملف فارغ. أعد اختيار صورة أو ملف PDF صالح.")
    if len(data) > max_bytes:
        raise UploadError(
            f"حجم الملف يتجاوز الحدّ المسموح ({max_bytes // (1024 * 1024)} ميغابايت)."
        )

    sniffed = sniff_content_type(data)
    if sniffed is None:
        raise UploadError("يُقبل فقط ملف PDF أو صورة JPEG/PNG لوصل الدفع.")
    mime, extension = sniffed

    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared and declared not in ALLOWED_CONTENT_TYPES:
        raise UploadError("نوع الملف غير مدعوم. استعمل PDF أو JPEG أو PNG.")
    if declared and declared != mime:
        raise UploadError("محتوى الملف لا يطابق نوعه المعلن. أعد اختيار الملف.")
    return mime, extension


def store_upload(
    data: bytes,
    *,
    original_name: str,
    declared_type: str,
    settings: Settings,
    subdir: str = "payments",
) -> StoredFile:
    """Validate and persist a file under ``APP_UPLOAD_DIR/<subdir>``."""
    mime, extension = validate_upload(
        data,
        original_name=original_name,
        declared_type=declared_type,
        max_bytes=settings.max_upload_bytes,
    )
    target_dir = Path(settings.upload_dir) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{subdir}/{secrets.token_hex(16)}{extension}"
    target = Path(settings.upload_dir) / stored_name
    target.write_bytes(data)
    target.chmod(0o640)

    return StoredFile(
        stored_name=stored_name,
        original_name=clean_original_name(original_name),
        content_type=mime,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def resolve_stored(settings: Settings, stored_name: str) -> Path | None:
    """Resolve a stored name inside the upload directory, blocking traversal."""
    root = Path(settings.upload_dir).resolve()
    candidate = (root / stored_name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "StoredFile",
    "UploadError",
    "clean_original_name",
    "resolve_stored",
    "sniff_content_type",
    "store_upload",
    "validate_upload",
]
