import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.grading.rubric import criterion_labels
from app.web.theme import chosen_theme

STATIC_DIR = Path(__file__).parent / "static"


def asset_version() -> str:
    """Short hash of the stylesheets, so a deploy's CSS is never served from a stale cache."""
    digest = hashlib.sha256()
    for name in ("tokens.css", "tmk.css"):
        digest.update((STATIC_DIR / name).read_bytes())
    return digest.hexdigest()[:10]


def display_title(title: str) -> str:
    """A paper title for display: PubMed brackets titles translated from another language."""
    inner = title.strip()
    end = "]." if inner.endswith("].") else "]"
    if inner.startswith("[") and inner.endswith(end) and inner.count("[") == 1:
        inner = inner[1 : -len(end)]
        return inner if inner.endswith((".", "?", "!")) else inner + "."
    return title


TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
TEMPLATES.env.globals["CRITERIA"] = criterion_labels()
TEMPLATES.env.globals["ASSET_VERSION"] = asset_version()
TEMPLATES.env.filters["headline"] = display_title
TEMPLATES.env.globals["chosen_theme"] = chosen_theme
