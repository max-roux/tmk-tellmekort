"""PMC full-text parser for `efetch db=pmc` JATS XML (SPEC.md §6.4). Pure.

An article is open access when it carries a Creative Commons licence. Its body is
reduced to section prose, dropping figures, tables, references and back matter, and
ordered Methods, Results and case descriptions first so truncation keeps what grading needs most.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass

CHARS_PER_TOKEN = 4  # rough estimate; no tokenizer needed for a budget
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
ALI_LICENSE_REF = "{http://www.niso.org/schemas/ali/1.0/}license_ref"

_SKIP_TAGS = {
    "fig",
    "fig-group",
    "table-wrap",
    "table-wrap-group",
    "supplementary-material",
    "fn-group",
    "ref-list",
    "media",
    "graphic",
}
_SKIP_SEC = re.compile(
    r"acknowledg|funding|conflicts? of interest|competing|author contribution|"
    r"data availability|supplementary|supporting information|ethics|abbreviation|"
    r"declaration|consent",
    re.I,
)
# (label, pattern on sec-type or title). Checked in order; first match wins.
_KINDS = (
    ("Methods", re.compile(r"method|materials|patients and|participants|study design", re.I)),
    ("Results", re.compile(r"result|findings", re.I)),
    ("Case", re.compile(r"case (presentation|report|description|series)|clinical case", re.I)),
    ("Introduction", re.compile(r"intro|background", re.I)),
    ("Discussion", re.compile(r"discussion", re.I)),
    ("Conclusions", re.compile(r"conclusion", re.I)),
)
_ORDER = ("Methods", "Results", "Case", "Introduction", "Discussion", "Conclusions", "Other")


@dataclass(frozen=True)
class PmcArticle:
    pmcid: str
    is_open_access: bool
    full_text: str | None  # None when not open access or the XML has no body


def _text(el: ET.Element) -> str:
    """Text of an element, skipping figure/table subtrees but keeping their tails."""

    def walk(e: ET.Element) -> Iterator[str]:
        if e.text:
            yield e.text
        for child in e:
            if child.tag not in _SKIP_TAGS:
                yield from walk(child)
            if child.tail:
                yield child.tail

    return " ".join("".join(walk(el)).split())


def _title(sec: ET.Element) -> str:
    title = sec.find("title")
    return _text(title) if title is not None else ""


def _paragraphs(sec: ET.Element) -> list[str]:
    out: list[str] = []
    for child in sec:
        if child.tag in _SKIP_TAGS or child.tag == "title":
            continue
        if child.tag == "sec":
            if title := _title(child):
                out.append(f"### {title}")
            out.extend(_paragraphs(child))
        elif child.tag in ("p", "list", "disp-quote", "boxed-text"):
            if text := _text(child):
                out.append(text)
    return out


def _kind(sec: ET.Element) -> str | None:
    """Section label, or None for sections to drop."""
    key = f"{sec.get('sec-type') or ''} {_title(sec)}"
    if _SKIP_SEC.search(key) or sec.get("sec-type") in {"COI-statement", "data-availability"}:
        return None
    for label, pattern in _KINDS:
        if pattern.search(key):
            return label
    return "Other"


def _is_open_access(article: ET.Element) -> bool:
    for lic in article.iterfind("front/article-meta/permissions/license"):
        if lic.get("license-type") == "open-access":
            return True
        refs = [lic.get(XLINK_HREF) or ""] + [r.text or "" for r in lic.iter(ALI_LICENSE_REF)]
        if any("creativecommons.org" in r for r in refs):
            return True
    return False


def _grouped(body: ET.Element) -> dict[str, list[str]]:
    """Paragraphs by section kind; loose paragraphs outside sections go first in Other."""
    groups: dict[str, list[str]] = {k: [] for k in _ORDER}
    loose: list[str] = []
    for child in body:
        if child.tag == "sec" and (kind := _kind(child)) is not None:
            groups[kind].extend(_paragraphs(child))
        elif child.tag == "p" and (text := _text(child)):
            loose.append(text)
    groups["Other"] = loose + groups["Other"]
    return groups


def _blocks(groups: dict[str, list[str]]) -> Iterator[str]:
    """A heading then its paragraphs, for each non-empty kind in priority order."""
    for kind in _ORDER:
        if groups[kind]:
            yield f"## {kind}"
            yield from groups[kind]


def body_text(body: ET.Element, max_tokens: int) -> str:
    """Body prose grouped by section kind, Methods and Results first, within the budget."""
    budget = max_tokens * CHARS_PER_TOKEN
    parts: list[str] = []
    used = 0
    for block in _blocks(_grouped(body)):
        if used + len(block) > budget:
            room = budget - used
            if room > 200:
                parts.append(block[:room].rsplit(" ", 1)[0] + " …")
            parts.append("[truncated]")
            break
        parts.append(block)
        used += len(block) + 2
    return "\n\n".join(parts)


def parse_pmc_xml(xml: bytes, max_tokens: int) -> list[PmcArticle]:
    root = ET.fromstring(xml)
    articles: list[PmcArticle] = []
    for article in root.iter("article"):
        pmcid = article.findtext("front/article-meta/article-id[@pub-id-type='pmcid']")
        if not pmcid:
            continue
        oa = _is_open_access(article)
        body = article.find("body")
        text = body_text(body, max_tokens) if oa and body is not None else None
        articles.append(PmcArticle(pmcid.strip(), oa, text or None))
    return articles
