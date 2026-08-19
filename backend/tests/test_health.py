from fastapi.testclient import TestClient

from draftkit.config import Settings
from draftkit.main import create_app


def test_health(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_data_dir_created(tmp_path):
    data_dir = tmp_path / "data"
    create_app(Settings(data_dir=data_dir))
    assert data_dir.is_dir()
