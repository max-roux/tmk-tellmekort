"""Parse seed paper references typed by a surgeon (SPEC.md §11.1). Pure."""

import re
from dataclasses import dataclass, field

# DOIs start with "10." and a registrant code; stop at whitespace, commas and semicolons.
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s,;]+)", re.I)
_PMID = re.compile(r"^(\d{1,9})$")
_PREFIX = re.compile(r"\b(?:pmid|doi)\s*:\s*", re.I)
_PUBMED_URL = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,9})", re.I)


@dataclass(frozen=True)
class SeedRefs:
    pmids: list[str] = field(default_factory=list)
    dois: list[str] = field(default_factory=list)
    unrecognised: list[str] = field(default_factory=list)


def parse_seed_refs(text: str) -> SeedRefs:
    """PMIDs, DOIs (bare, doi: or doi.org URLs) and PubMed URLs, one or many per line.

    Order is kept and duplicates dropped.
    """
    pmids: list[str] = []
    dois: list[str] = []
    bad: list[str] = []
    for token in re.split(r"[\s,;]+", _PREFIX.sub("", text).strip()):
        if not token:
            continue
        if m := _PUBMED_URL.search(token):
            found, bucket = m.group(1), pmids
        elif m := _DOI.search(token):
            found, bucket = m.group(1).rstrip(".)").lower(), dois
        elif m := _PMID.match(token):
            found, bucket = m.group(1), pmids
        else:
            found, bucket = token, bad
        if found not in bucket:
            bucket.append(found)
    return SeedRefs(pmids, dois, bad)
