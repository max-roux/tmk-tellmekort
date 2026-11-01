"""Narrowing: which new papers are worth grading this week (SPEC.md §6.3). Pure."""

from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt

Matrix = npt.NDArray[np.float64]


def _unit_rows(m: Matrix) -> Matrix:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return np.divide(m, norms, out=np.zeros_like(m), where=norms > 0)


def narrow_scores(
    papers: Mapping[str, Sequence[float]], references: Sequence[Sequence[float]]
) -> dict[str, float]:
    """For each paper, the max cosine similarity to any reference vector.

    References are the specialty anchor plus every active user's profile vector.
    """
    if not papers or not references:
        return {pmid: 0.0 for pmid in papers}
    pmids = list(papers)
    p = _unit_rows(np.asarray([papers[k] for k in pmids], dtype=np.float64))
    r = _unit_rows(np.asarray(references, dtype=np.float64))
    best = (p @ r.T).max(axis=1)
    return {pmid: float(s) for pmid, s in zip(pmids, best, strict=True)}


def select_for_grading(scores: Mapping[str, float], limit: int) -> set[str]:
    """Top `limit` papers by score.

    Ties break on PMID, higher (newer) first, so selection is deterministic. Users' seed
    papers are not forced in: they shape the profile, but are never recommended back.
    """
    ranked = sorted(scores, key=lambda pmid: (scores[pmid], pmid), reverse=True)
    return set(ranked[:limit])
