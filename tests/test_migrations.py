import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.db


def test_upgrade_head_enables_pgvector_and_is_rerunnable(database_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # idempotent

    engine = create_engine(database_url)
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        has_papers = conn.execute(text("SELECT to_regclass('papers')")).scalar()
    engine.dispose()
    assert version is not None
    assert has_papers == "papers"
