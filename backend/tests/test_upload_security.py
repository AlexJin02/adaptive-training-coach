from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.services import media, uploads


def _media_import_count(client: TestClient) -> int:
    response = client.get("/api/v1/data/backup")
    assert response.status_code == 200
    return len(response.json()["data"]["media_imports"])


def test_upload_limits_are_explicit() -> None:
    assert uploads.SCREENSHOT_MAX_BYTES == 10 * 1024 * 1024
    assert uploads.AUDIO_MAX_BYTES == 25 * 1024 * 1024
    assert uploads.RESTORE_MAX_BYTES == 25 * 1024 * 1024


def test_screenshot_rejects_oversize_before_persistence_or_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "SCREENSHOT_MAX_BYTES", 8)
    monkeypatch.setattr(
        media,
        "extract_image",
        lambda *_args, **_kwargs: pytest.fail("provider service must not be called"),
    )
    response = client.post(
        "/api/v1/ai/workouts/extract-image",
        data={"retain_raw": "true"},
        files={"image": ("run.png", b"\x89PNG\r\n\x1a\nX", "image/png")},
    )
    assert response.status_code == 413
    assert _media_import_count(client) == 0


def test_screenshot_rejects_spoofed_image_before_persistence_or_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        media,
        "extract_image",
        lambda *_args, **_kwargs: pytest.fail("provider service must not be called"),
    )
    response = client.post(
        "/api/v1/ai/workouts/extract-image",
        data={"retain_raw": "true"},
        files={"image": ("not-an-image.png", b"arbitrary bytes", "image/png")},
    )
    assert response.status_code == 415
    assert _media_import_count(client) == 0


def test_audio_rejects_oversize_before_persistence_or_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "AUDIO_MAX_BYTES", 4)
    monkeypatch.setattr(
        media,
        "transcribe_audio",
        lambda *_args, **_kwargs: pytest.fail("provider service must not be called"),
    )
    response = client.post(
        "/api/v1/ai/notes/transcribe",
        data={"retain_raw": "true"},
        files={"audio": ("note.webm", b"\x1aE\xdf\xa3X", "audio/webm")},
    )
    assert response.status_code == 413
    assert _media_import_count(client) == 0


def test_audio_rejects_spoofed_mime_before_persistence_or_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        media,
        "transcribe_audio",
        lambda *_args, **_kwargs: pytest.fail("provider service must not be called"),
    )
    response = client.post(
        "/api/v1/ai/notes/transcribe",
        data={"retain_raw": "true"},
        files={"audio": ("note.webm", b"arbitrary bytes", "audio/webm")},
    )
    assert response.status_code == 415
    assert _media_import_count(client) == 0


def test_restore_rejects_wrong_type_before_parsing(client: TestClient) -> None:
    response = client.post(
        "/api/v1/data/restore",
        files={"backup": ("backup.txt", b"{}", "text/plain")},
    )
    assert response.status_code == 415


def test_restore_rejects_oversize_before_parsing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "RESTORE_MAX_BYTES", 8)
    response = client.post(
        "/api/v1/data/restore",
        files={
            "backup": (
                "backup.json",
                json.dumps({"schema_version": "1.0", "data": {}}),
                "application/json",
            )
        },
    )
    assert response.status_code == 413
