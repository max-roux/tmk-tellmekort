from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

SETTINGS = Settings(_env_file=None, admin_email="privacy@example.com")  # type: ignore[call-arg]


def client(settings: Settings = SETTINGS) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
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


def test_privacy_note_names_google_when_gmail_sends_the_email() -> None:
    gmail = Settings(_env_file=None, smtp_host="smtp.gmail.com")  # type: ignore[call-arg]
    page = client(gmail).get("/privacy").text
    assert "Google" in page and "Postmark" not in page
