"""Where a form may send the user back to."""


def local_path(target: str, fallback: str) -> str:
    """Only same-site paths, so `next` cannot send the user elsewhere."""
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback
