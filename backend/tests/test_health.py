from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_startup_creates_data_directory_but_no_database(tmp_path):
    data_dir = tmp_path / "runtime"
    settings = Settings(_env_file=None, data_dir=data_dir)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert client.get("/openapi.json").json()["info"]["title"] == "Cue Player"
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert data_dir.is_dir()
        assert not (data_dir / "app.db").exists()
        other = client.get("/api/health", headers={"Origin": "https://example.com"})
        assert "access-control-allow-origin" not in other.headers
