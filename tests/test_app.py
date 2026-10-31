from collections.abc import Iterator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import create_app


def _client_with_session(session: MagicMock) -> TestClient:
    app = create_app()

    def override() -> Iterator[MagicMock]:
        yield session

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_home_renders() -> None:
    resp = _client_with_session(MagicMock()).get("/")
    assert resp.status_code == 200
    assert "Maxfac Papers" in resp.text


def test_healthz_ok() -> None:
    resp = _client_with_session(MagicMock()).get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


def test_healthz_db_down() -> None:
    session = MagicMock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))
    resp = _client_with_session(session).get("/healthz")
    assert resp.status_code == 503
    assert resp.json()["db"] == "unreachable"
