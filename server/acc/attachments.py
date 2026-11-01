"""Images the user attaches (screenshots) and design variants picked for implementation.

Uploads are checked by their first bytes, not by name or claimed type: only real PNG, JPEG,
WebP or GIF data is stored. An attachment id is either an upload id (32 hex chars) or
"design:<message id>:<n>" for a rendered design variant.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from acc import config

MAX_BYTES = 10 * 1024 * 1024
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
_DESIGN_ID = re.compile(r"^design:(\d+):(\d+)$")


class AttachmentError(ValueError):
    pass


def sniff(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    return None


def save_upload(data: bytes, name: str) -> dict[str, str]:
    if len(data) > MAX_BYTES:
        raise AttachmentError("Görsel 10 MB'tan büyük olamaz.")
    kind = sniff(data)
    if kind is None:
        raise AttachmentError("Yalnızca PNG, JPEG, WebP veya GIF görseller eklenebilir.")
    mime, ext = kind
    upload_id = uuid.uuid4().hex
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (config.UPLOADS_DIR / f"{upload_id}.{ext}").write_bytes(data)
    return {"id": upload_id, "name": name[:120] or f"görsel.{ext}", "mime": mime}


def upload_path(upload_id: str) -> Path | None:
    if not _UPLOAD_ID.match(upload_id):
        return None
    found = sorted(config.UPLOADS_DIR.glob(f"{upload_id}.*"))
    return found[0] if found else None


def design_files(message_id: int, n: int) -> list[Path]:
    folder = config.DESIGNS_DIR / str(message_id)
    return [p for p in (folder / f"v{n}.png", folder / f"v{n}.html") if p.exists()]


def resolve(attachment_id: str) -> list[Path]:
    """Files behind an attachment id; raises for unknown ids."""
    if path := upload_path(attachment_id):
        return [path]
    if m := _DESIGN_ID.match(attachment_id):
        files = design_files(int(m[1]), int(m[2]))
        if files:
            return files
    raise AttachmentError(f"Ek bulunamadı: {attachment_id}")


def prompt_block(ids: list[str] | None) -> str:
    """Tells the model which files to look at (with the Read tool)."""
    if not ids:
        return ""
    lines = []
    for attachment_id in ids:
        try:
            files = resolve(attachment_id)
        except AttachmentError:
            continue
        label = (
            "seçilen tasarım (ekran görüntüsü ve HTML'i)"
            if attachment_id.startswith("design:")
            else "görsel"
        )
        lines.append(f"- {label}: " + " · ".join(str(f) for f in files))
    if not lines:
        return ""
    return "KULLANICININ EKLERİ (Read aracıyla aç ve dikkate al):\n" + "\n".join(lines) + "\n\n"


def read_dirs() -> list[Path]:
    for d in (config.UPLOADS_DIR, config.DESIGNS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return [config.UPLOADS_DIR, config.DESIGNS_DIR]
