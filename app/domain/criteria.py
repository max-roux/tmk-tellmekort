"""The grading criteria (SPEC.md §2)."""

# Properties of the paper, scored by the LLM and shared by all users.
INTRINSIC_CRITERIA = ("proof_strength", "novelty", "depth", "practical_usefulness")
# Per-user, computed from embeddings, never by the LLM.
ALL_CRITERIA = ("pertinence", *INTRINSIC_CRITERIA)
