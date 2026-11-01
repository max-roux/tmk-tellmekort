from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.db.models import Paper
from app.grading.rubric import criterion_guides

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")


def paper_url(paper: Paper) -> str:
    """The publisher's page via DOI, else PubMed."""
    if paper.doi:
        return f"https://doi.org/{paper.doi}"
    return f"https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}/"


TEMPLATES.env.globals["CRITERIA"] = [("pertinence", "Pertinence")] + [
    (g.key, g.name) for g in criterion_guides()
]
TEMPLATES.env.filters["paper_url"] = paper_url
