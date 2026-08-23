from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.ai import (
    AIUnavailableError,
    extract_workout_from_image,
    transcribe_training_note,
)
from app.config import get_settings


def transcribe_audio(
    db: Session,
    raw: bytes,
    *,
    original_filename: str | None,
    content_type: str | None,
    retain_raw: bool,
) -> str:
    settings = get_settings()
    retain_setting = db.get(models.AppSetting, "retain_audio")
    retain = retain_raw or (
        bool(retain_setting.value) if retain_setting else settings.retain_raw_audio
    )
    media = models.MediaImport(
        kind="AUDIO",
        status="UPLOADED",
        original_filename=original_filename,
        retain_raw=retain,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    try:
        transcript = transcribe_training_note(
            raw,
            original_filename or "training-note.webm",
            content_type or "audio/webm",
        )
        if retain:
            path = (
                settings.media_dir
                / f"audio-{media.id}-{Path(original_filename or 'note.webm').name}"
            )
            path.write_bytes(raw)
            media.local_path = str(path)
        media.status = "EXTRACTED"
        media.extraction = {"transcript": transcript}
        db.commit()
        return transcript
    except AIUnavailableError as exc:
        media.status = "FAILED"
        media.error = str(exc)
        db.commit()
        raise


def extract_image(
    db: Session,
    raw: bytes,
    *,
    original_filename: str | None,
    content_type: str | None,
    retain_raw: bool,
) -> dict[str, object]:
    media = models.MediaImport(
        kind="SCREENSHOT",
        status="UPLOADED",
        original_filename=original_filename,
        retain_raw=retain_raw,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    settings = get_settings()
    stored_retain = db.get(models.AppSetting, "retain_screenshots")
    effective_retain = retain_raw or (
        bool(stored_retain.value) if stored_retain else settings.retain_raw_screenshots
    )
    try:
        extraction = extract_workout_from_image(raw, content_type or "image/png")
        payload = extraction.model_dump(mode="json")
        if effective_retain:
            path = (
                settings.media_dir
                / f"screenshot-{media.id}-{Path(original_filename or 'upload').name}"
            )
            path.write_bytes(raw)
            media.local_path = str(path)
            media.retain_raw = True
        media.extraction = payload
        media.status = "EXTRACTED"
        db.commit()
        return payload
    except AIUnavailableError as exc:
        media.status = "FAILED"
        media.error = str(exc)
        db.commit()
        raise
