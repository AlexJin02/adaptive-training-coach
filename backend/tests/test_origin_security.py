from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app.config import Settings
from app.services import media


def test_cross_origin_restore_is_blocked_and_allowed_origin_succeeds(
    client: TestClient,
) -> None:
    payload = client.get("/api/v1/data/backup").json()
    payload["data"]["athlete_profiles"][0]["display_name"] = "Trusted restore"
    upload = {"backup": ("backup.json", json.dumps(payload), "application/json")}

    blocked = client.post(
        "/api/v1/data/restore",
        headers={"Origin": "https://attacker.invalid"},
        files=upload,
    )
    assert blocked.status_code == 403
    assert client.get("/api/v1/athlete/profile").json()["display_name"] == "Alex"

    allowed = client.post(
        "/api/v1/data/restore",
        headers={"Origin": "http://localhost:5173"},
        files=upload,
    )
    assert allowed.status_code == 200
    assert client.get("/api/v1/athlete/profile").json()["display_name"] == "Trusted restore"

    local_production = client.post(
        "/api/v1/data/restore",
        headers={"Origin": "http://localhost:8000"},
        files=upload,
    )
    assert local_production.status_code == 200


def test_cross_origin_media_upload_is_blocked_before_service_and_localhost_works(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bytes] = []

    def fake_extract(_db, raw: bytes, **_kwargs):  # noqa: ANN001
        calls.append(raw)
        return {"workout_kind": "RUNNING", "session_type": "Easy"}

    monkeypatch.setattr(media, "extract_image", fake_extract)
    upload = {"image": ("run.png", b"\x89PNG\r\n\x1a\n", "image/png")}

    blocked = client.post(
        "/api/v1/ai/workouts/extract-image",
        headers={"Origin": "https://attacker.invalid"},
        files=upload,
    )
    assert blocked.status_code == 403
    assert calls == []

    allowed = client.post(
        "/api/v1/ai/workouts/extract-image",
        headers={"Origin": "http://localhost:5173"},
        files=upload,
    )
    assert allowed.status_code == 200
    assert calls == [b"\x89PNG\r\n\x1a\n"]


@pytest.mark.parametrize("origin", ["http://localhost:8000", "http://127.0.0.1:8000"])
def test_local_production_origins_allow_every_mutating_http_method(
    client: TestClient, origin: str
) -> None:
    headers = {"Origin": origin}

    assert client.post("/api/v1/completed-sessions", headers=headers, json={}).status_code == 422
    assert (
        client.patch("/api/v1/planned-sessions/999999", headers=headers, json={}).status_code == 404
    )
    assert client.delete("/api/v1/planned-sessions/999999", headers=headers).status_code == 404
    assert (
        client.put("/api/v1/climbing/route-benchmark", headers=headers, json={}).status_code != 403
    )


def test_configured_openai_key_enables_planner_capability(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(_env_file=None, openai_api_key="test-key")
    monkeypatch.setattr(api_module, "get_settings", lambda: settings)

    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    assert response.json()["ai_planner"] is True
