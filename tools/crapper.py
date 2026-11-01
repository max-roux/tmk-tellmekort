"""CRAP score per function: complexity^2 * (1 - coverage)^3 + complexity.

Complexity is radon's cyclomatic complexity; coverage is the share of the function's
executable lines that the test suite runs. High CRAP = complex and untested.

    uv run python tools/crapper.py            # run the tests with coverage, then report
    uv run python tools/crapper.py --no-run   # reuse var/coverage.json
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from radon.complexity import cc_visit
from radon.visitors import Class, Function

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_JSON = ROOT / "var" / "coverage.json"
SKIP = ("app/db/migrations/",)


@dataclass(frozen=True)
class Score:
    where: str
    complexity: int
    coverage: float

    @property
    def crap(self) -> float:
        return self.complexity**2 * (1 - self.coverage) ** 3 + self.complexity


def crap_scores(path: str, source: str, executed: set[int], missing: set[int]) -> list[Score]:
    scores = []
    blocks = cc_visit(source)
    functions = [b for b in blocks if isinstance(b, Function)]
    functions += [m for b in blocks if isinstance(b, Class) for m in b.methods]
    # radon lists methods both under their class and on their own; keep one of each.
    unique = {(f.lineno, f.fullname): f for f in functions}
    for f in unique.values():
        lines = set(range(f.lineno, f.endline + 1))
        ran, not_ran = len(lines & executed), len(lines & missing)
        coverage = ran / (ran + not_ran) if ran + not_ran else 1.0
        scores.append(Score(f"{path}:{f.lineno} {f.fullname}", f.complexity, coverage))
    return scores


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=10.0)
    parser.add_argument("--no-run", action="store_true")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    if not args.no_run:
        COVERAGE_JSON.parent.mkdir(exist_ok=True)
        subprocess.run(
            ["pytest", "-q", "--cov=app", f"--cov-report=json:{COVERAGE_JSON}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    files = json.loads(COVERAGE_JSON.read_text())["files"]
    scores: list[Score] = []
    for path, data in files.items():
        if path.startswith(SKIP):
            continue
        source = (ROOT / path).read_text()
        scores += crap_scores(path, source, set(data["executed_lines"]), set(data["missing_lines"]))
    scores.sort(key=lambda s: s.crap, reverse=True)
    over = [s for s in scores if s.crap >= args.threshold]
    for s in scores[: max(args.top, len(over))]:
        flag = "!!" if s.crap >= args.threshold else "  "
        print(f"{flag} CRAP {s.crap:6.1f}  cc {s.complexity:2d}  cov {s.coverage:5.0%}  {s.where}")
    print(f"\n{len(over)} of {len(scores)} functions at or above CRAP {args.threshold:g}.")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
