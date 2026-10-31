import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.db


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_head_enables_pgvector_and_is_rerunnable(database_url: str) -> None:
    cfg = _alembic_config(database_url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # idempotent

    engine = create_engine(database_url)
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    engine.dispose()
    assert version is not None
