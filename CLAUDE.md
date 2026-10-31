# CLAUDE.md

Maxfac Paper Recommender: weekly LLM-graded research-paper recommendations for a maxillofacial surgeon.

**Read `SPEC.md` first.** It is the source of truth for scope, data model, grading rubric, ranking and build order. If an implementation choice contradicts SPEC.md, stop and ask, or update SPEC.md in the same change after the user agrees.

## How to work
- Build in the milestone order of SPEC.md §18. Finish and demo one milestone before starting the next.
- Keep `app/domain/` pure (no DB, HTTP or clock calls; pass `now` in). All ranking, eligibility and pick logic lives there and is unit-tested.
- External APIs (NCBI, Anthropic, Voyage, Postmark) go behind thin clients. Tests use recorded fixtures; never call live APIs in tests.
- Every pipeline step must be idempotent and safe to re-run.
- Any change to the rubric text bumps `RUBRIC_VERSION` in `app/grading/rubric.py`.
- Never store patient data. Never log API keys or full email tokens.

## Commands
- `uv run pytest`: tests
- `uv run ruff check . && uv run ruff format .`: lint and format
- `uv run mypy app`: type check
- `uv run alembic upgrade head`: migrate
- `uv run python cli.py --help`: ingest, grade, regrade, calibrate, send-test

## Conventions
- Python 3.12, SQLAlchemy 2.x typed ORM, pydantic-settings for config.
- UTC in the database; convert to the user's timezone only at the edges (scheduling, display).
- Small commits, one concern each, tests alongside the code.
