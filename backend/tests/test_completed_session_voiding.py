from datetime import date

import pytest
from fastapi.testclient import TestClient


def test_delete_completed_session_permanently_removes_and_recalculates_evidence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.application.core.analyse_completed_session_with_ai",
        lambda *_args, **_kwargs: None,
    )
    plan_response = client.post(
        "/api/v1/planned-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Race",
            "title": "10K race",
            "planned_duration_minutes": 45,
            "planned_distance_km": 10,
            "target_rpe": 8,
        },
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.json()["id"]

    saved = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Race",
            "duration_minutes": 42,
            "distance_km": 10,
            "rpe": 8,
            "planned_session_id": plan_id,
        },
    )
    assert saved.status_code == 201
    session_id = saved.json()["id"]
    assert client.get("/api/v1/athlete-state/running").json()["estimated_10k"]["value"]

    deleted = client.delete(f"/api/v1/completed-sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": session_id}
    assert client.get("/api/v1/completed-sessions").json()["total"] == 0
    assert client.get("/api/v1/athlete-state/running").json()["estimated_10k"]["value"] is None
    plans = client.get("/api/v1/planned-sessions").json()["items"]
    assert plans[0]["status"] == "PLANNED"
    assert client.delete(f"/api/v1/completed-sessions/{session_id}").status_code == 404


def test_delete_missing_completed_session_returns_404(client: TestClient) -> None:
    response = client.delete("/api/v1/completed-sessions/99999")
    assert response.status_code == 404
