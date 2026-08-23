from pathlib import Path

from fastapi.testclient import TestClient

from app import main as main_module


def test_built_frontend_and_spa_routes_share_the_api_origin(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>Remote coach</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("window.coach = true", encoding="utf-8")
    monkeypatch.setattr(main_module, "FRONTEND_DIST", dist)

    root = client.get("/")
    spa = client.get("/today")
    asset = client.get("/assets/app.js")
    health = client.get("/api/v1/health")
    missing_api = client.get("/api/v1/not-a-real-endpoint")

    assert root.status_code == 200
    assert root.headers["content-type"].startswith("text/html")
    assert "Remote coach" in root.text
    assert spa.status_code == 200
    assert "Remote coach" in spa.text
    assert asset.status_code == 200
    assert asset.text == "window.coach = true"
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert missing_api.status_code == 404


def test_frontend_hosting_does_not_escape_the_dist_directory(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>Coach</html>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not public", encoding="utf-8")
    monkeypatch.setattr(main_module, "FRONTEND_DIST", dist)

    response = client.get("/%2e%2e/secret.txt")

    assert response.status_code == 404
    assert "not public" not in response.text
