from __future__ import annotations

from fastapi import UploadFile

SCREENSHOT_MAX_BYTES = 10 * 1024 * 1024
AUDIO_MAX_BYTES = 25 * 1024 * 1024
RESTORE_MAX_BYTES = 25 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024


class UploadValidationError(ValueError):
    pass


class UploadTooLargeError(UploadValidationError):
    pass


class UnsupportedUploadTypeError(UploadValidationError):
    pass


class EmptyUploadError(UploadValidationError):
    pass


async def _read_bounded(upload: UploadFile, *, max_bytes: int, label: str) -> bytes:
    data = bytearray()
    while True:
        remaining_with_sentinel = max_bytes - len(data) + 1
        chunk = await upload.read(min(UPLOAD_CHUNK_BYTES, remaining_with_sentinel))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise UploadTooLargeError(f"{label} exceeds the {max_bytes // (1024 * 1024)} MiB limit")
    if not data:
        raise EmptyUploadError(f"{label} is empty")
    return bytes(data)


def _mime(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


def _image_family(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    return None


async def read_screenshot(upload: UploadFile) -> bytes:
    mime = _mime(upload)
    expected_family = {
        "image/png": "png",
        "image/x-png": "png",
        "image/jpeg": "jpeg",
        "image/jpg": "jpeg",
        "image/gif": "gif",
        "image/webp": "webp",
    }.get(mime)
    if expected_family is None:
        raise UnsupportedUploadTypeError(
            "Screenshot must be PNG, JPEG, GIF, or WebP with an image MIME type"
        )
    raw = await _read_bounded(upload, max_bytes=SCREENSHOT_MAX_BYTES, label="Screenshot")
    if _image_family(raw) != expected_family:
        raise UnsupportedUploadTypeError("Screenshot MIME type does not match its file signature")
    return raw


def _audio_family(raw: bytes) -> str | None:
    if len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WAVE":
        return "wav"
    if raw.startswith(b"\x1aE\xdf\xa3"):
        return "webm"
    if raw.startswith(b"ID3") or (len(raw) >= 2 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0):
        return "mpeg"
    if len(raw) >= 12 and raw[4:8] == b"ftyp":
        return "mp4"
    if raw.startswith(b"OggS"):
        return "ogg"
    if raw.startswith(b"fLaC"):
        return "flac"
    return None


async def read_audio(upload: UploadFile) -> bytes:
    mime = _mime(upload)
    expected_family = {
        "audio/mpeg": "mpeg",
        "audio/mp3": "mpeg",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/wave": "wav",
        "audio/webm": "webm",
        "audio/mp4": "mp4",
        "audio/m4a": "mp4",
        "audio/x-m4a": "mp4",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/x-flac": "flac",
    }.get(mime)
    if expected_family is None:
        raise UnsupportedUploadTypeError("Audio upload must use a supported audio MIME type")
    raw = await _read_bounded(upload, max_bytes=AUDIO_MAX_BYTES, label="Audio upload")
    if _audio_family(raw) != expected_family:
        raise UnsupportedUploadTypeError("Audio MIME type does not match its file signature")
    return raw


async def read_restore_json(upload: UploadFile) -> bytes:
    mime = _mime(upload)
    has_json_name = bool(upload.filename and upload.filename.lower().endswith(".json"))
    if mime != "application/json" and not has_json_name:
        raise UnsupportedUploadTypeError(
            "Backup must use application/json or have a .json filename"
        )
    return await _read_bounded(upload, max_bytes=RESTORE_MAX_BYTES, label="Backup")
