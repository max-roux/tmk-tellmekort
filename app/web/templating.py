import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.grading.rubric import criterion_labels

STATIC_DIR = Path(__file__).parent / "static"


def asset_version() -> str:
    """Short hash of the stylesheets, so a deploy's CSS is never served from a stale cache."""
    digest = hashlib.sha256()
    for name in ("tokens.css", "tmk.css"):
        digest.update((STATIC_DIR / name).read_bytes())
    return digest.hexdigest()[:10]


TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
TEMPLATES.env.globals["CRITERIA"] = criterion_labels()
TEMPLATES.env.globals["ASSET_VERSION"] = asset_version()
