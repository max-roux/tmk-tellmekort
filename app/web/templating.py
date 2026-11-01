from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.grading.rubric import criterion_labels

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
TEMPLATES.env.globals["CRITERIA"] = criterion_labels()
