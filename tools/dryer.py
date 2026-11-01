"""Find near-duplicate functions: rank = similarity of their token shapes (0-1).

Identifiers become N, numbers 0 and strings S, so two functions that differ only in
names and literals rank 1.0. Very short functions are ignored as noise.

    uv run python tools/dryer.py [--threshold 0.8] [--min-tokens 40]
"""

import argparse
import ast
import io
import itertools
import keyword
import sys
import tokenize
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = ("migrations",)
_IGNORED = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}


@dataclass(frozen=True)
class Unit:
    where: str
    shape: tuple[str, ...]


def shape(source: str) -> tuple[str, ...]:
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in _IGNORED or tok.type == tokenize.ENDMARKER:
            continue
        if tok.type == tokenize.NAME and not keyword.iskeyword(tok.string):
            out.append("N")
        elif tok.type == tokenize.NUMBER:
            out.append("0")
        elif tok.type == tokenize.STRING:
            out.append("S")
        else:
            out.append(tok.string)
    return tuple(out)


def units(path: Path, rel: str) -> list[Unit]:
    source = path.read_text()
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            body = ast.get_source_segment(source, node) or ""
            # Docstrings say what differs; compare the code only.
            if ast.get_docstring(node):
                doc = node.body[0]
                body = body.replace(ast.get_source_segment(source, doc) or "", "", 1)
            found.append(Unit(f"{rel}:{node.lineno} {node.name}", shape(body)))
    return found


def rank(a: Unit, b: Unit) -> float:
    return SequenceMatcher(None, a.shape, b.shape, autojunk=False).ratio()


def duplicates(
    all_units: list[Unit], threshold: float, min_tokens: int
) -> list[tuple[float, Unit, Unit]]:
    big = [u for u in all_units if len(u.shape) >= min_tokens]
    pairs = []
    for a, b in itertools.combinations(big, 2):
        sm = SequenceMatcher(None, a.shape, b.shape, autojunk=False)
        if sm.real_quick_ratio() >= threshold and sm.quick_ratio() >= threshold:
            r = sm.ratio()
            if r >= threshold:
                pairs.append((r, a, b))
    return sorted(pairs, key=lambda p: p[0], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--min-tokens", type=int, default=40)
    parser.add_argument("paths", nargs="*", default=["app"])
    args = parser.parse_args()
    all_units = []
    for base in args.paths:
        for path in sorted((ROOT / base).rglob("*.py")):
            rel = str(path.relative_to(ROOT))
            if not any(s in rel for s in SKIP):
                all_units += units(path, rel)
    found = duplicates(all_units, args.threshold, args.min_tokens)
    for r, a, b in found:
        print(f"{r:.2f}  {a.where}  <->  {b.where}")
    print(f"\n{len(found)} pairs at rank {args.threshold:g} or above ({len(all_units)} functions).")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
