import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import get_settings


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of a reachable Postgres; skips `db`-marked tests when none is running."""
    url = get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Postgres not reachable at DATABASE_URL (run: docker compose up -d)")
    finally:
        engine.dispose()
    return url
