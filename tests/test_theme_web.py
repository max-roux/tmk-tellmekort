from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import create_app


def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: MagicMock()
    return TestClient(app, base_url="https://tmk.test")


def test_pages_follow_the_device_until_an_edition_is_chosen() -> None:
    html = client().get("/login").text
    assert '<html lang="en">' in html and 'content="light dark"' in html
    assert 'value="auto" aria-pressed="true"' in html


def test_choosing_evening_sets_a_cookie_and_returns_to_the_page() -> None:
    c = client()
    resp = c.post("/theme", data={"theme": "dark", "next": "/login"}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/login"
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith("theme=dark;") and "HttpOnly" in cookie and "Secure" in cookie
    html = c.get("/login").text
    assert '<html lang="en" data-theme="dark">' in html
    assert 'value="dark" aria-pressed="true"' in html


def test_auto_clears_the_choice() -> None:
    c = client()
    c.post("/theme", data={"theme": "light", "next": "/login"})
    assert 'data-theme="light"' in c.get("/login").text
    c.post("/theme", data={"theme": "auto", "next": "/login"})
    assert "data-theme" not in c.get("/login").text


def test_bad_values_are_refused_or_ignored() -> None:
    c = client()
    assert c.post("/theme", data={"theme": "sepia"}).status_code == 422
    resp = c.post(
        "/theme", data={"theme": "light", "next": "//evil.example.com/"}, follow_redirects=False
    )
    assert resp.headers["location"] == "/"
    c.cookies.set("theme", '"><script>', domain="tmk.test")
    assert "data-theme" not in c.get("/login").text
