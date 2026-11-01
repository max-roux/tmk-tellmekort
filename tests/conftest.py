from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of a throwaway `<db>_test` database, created if needed.

    Skips `db`-marked tests when Postgres is not running.
    """
    url = make_url(get_settings().database_url)
    test_url = url.set(database=f"{url.database}_test")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_url.database}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    except OperationalError:
        pytest.skip("Postgres not reachable at DATABASE_URL (run: docker compose up -d)")
    finally:
        admin.dispose()
    return test_url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def migrated_url(database_url: str) -> str:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    return database_url


@pytest.fixture
def db_session(migrated_url: str) -> Iterator[Session]:
    """A session on a migrated test database with all tables emptied first."""
    engine = create_engine(migrated_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE papers, users, login_attempts, llm_spend, grading_batches CASCADE"))
    with Session(engine) as session:
        yield session
    engine.dispose()
