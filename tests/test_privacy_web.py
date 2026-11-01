from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

SETTINGS = Settings(_env_file=None, admin_email="privacy@example.com")  # type: ignore[call-arg]


def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    return TestClient(app)


def test_privacy_note_is_public_and_names_every_sub_processor() -> None:
    page = client().get("/privacy")
    assert page.status_code == 200
    for name in ("Render", "Anthropic", "Voyage AI", "Postmark"):
        assert name in page.text
    assert "Frankfurt" in page.text and "privacy@example.com" in page.text
    assert "patient" in page.text.lower()  # states that no patient data is stored


def test_privacy_note_is_linked_from_sign_in() -> None:
    assert 'href="/privacy"' in client().get("/login").text
