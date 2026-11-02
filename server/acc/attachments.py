"""What the user attaches: screenshots, text files (an app idea or spec as .md / .txt) and
design variants picked for implementation.

Uploads are checked by their bytes, not by claimed type: images must really be PNG, JPEG,
WebP or GIF; text files must be UTF-8 without binary content. An attachment id is either an
upload id (32 hex chars) or "design:<message id>:<n>" for a rendered design variant.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from acc import config

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
TEXT_TYPES = {"md": "text/markdown", "markdown": "text/markdown", "txt": "text/plain"}
NAME_SUFFIX = ".name"  # original file name, kept next to the upload
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


def sniff_text(data: bytes, name: str) -> tuple[str, str] | None:
    """A markdown / text file: by extension, and only if it really is UTF-8 text."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in TEXT_TYPES or b"\x00" in data:
        return None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return TEXT_TYPES[ext], "md" if ext == "markdown" else ext


def save_upload(data: bytes, name: str) -> dict[str, str]:
    image = sniff(data)
    text = None if image else sniff_text(data, name)
    if image is None and text is None:
        raise AttachmentError(
            "Yalnızca görsel (PNG, JPEG, WebP, GIF) ya da metin dosyası (.md, .txt) eklenebilir."
        )
    if image and len(data) > MAX_BYTES:
        raise AttachmentError("Görsel 10 MB'tan büyük olamaz.")
    if text and len(data) > MAX_TEXT_BYTES:
        raise AttachmentError("Metin dosyası 1 MB'tan büyük olamaz.")
    mime, ext = image or text
    upload_id = uuid.uuid4().hex
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (config.UPLOADS_DIR / f"{upload_id}.{ext}").write_bytes(data)
    clean = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip()[:120] or f"ek.{ext}"
    (config.UPLOADS_DIR / f"{upload_id}{NAME_SUFFIX}").write_text(clean, encoding="utf-8")
    return {"id": upload_id, "name": clean, "mime": mime}


def upload_path(upload_id: str) -> Path | None:
    if not _UPLOAD_ID.match(upload_id):
        return None
    found = sorted(p for p in config.UPLOADS_DIR.glob(f"{upload_id}.*") if p.suffix != NAME_SUFFIX)
    return found[0] if found else None


def is_text(path: Path) -> bool:
    return path.suffix.lstrip(".") in TEXT_TYPES


def describe(attachment_id: str) -> dict[str, str]:
    """For the UI: what kind of attachment this is and what it was called."""
    if attachment_id.startswith("design:"):
        return {"id": attachment_id, "kind": "design", "name": "tasarım"}
    path = upload_path(attachment_id)
    name_file = config.UPLOADS_DIR / f"{attachment_id}{NAME_SUFFIX}"
    name = name_file.read_text(encoding="utf-8") if name_file.exists() else ""
    kind = "text" if path and is_text(path) else "image"
    return {
        "id": attachment_id,
        "kind": kind,
        "name": name or ("metin" if kind == "text" else "görsel"),
    }


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
        if attachment_id.startswith("design:"):
            label = "seçilen tasarım (ekran görüntüsü ve HTML'i)"
        elif is_text(files[0]):
            label = "metin dosyası (ör. uygulama fikri ya da spec; baştan sona oku)"
        else:
            label = "görsel"
        lines.append(f"- {label}: " + " · ".join(str(f) for f in files))
    if not lines:
        return ""
    return "KULLANICININ EKLERİ (Read aracıyla aç ve dikkate al):\n" + "\n".join(lines) + "\n\n"


def read_dirs() -> list[Path]:
    for d in (config.UPLOADS_DIR, config.DESIGNS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return [config.UPLOADS_DIR, config.DESIGNS_DIR]
