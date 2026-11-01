from tools.crapper import crap_scores

SOURCE = """\
def simple(x):
    return x + 1


def branchy(x):
    if x > 1:
        return 1
    if x > 2:
        return 2
    return 3
"""


def test_crap_by_hand() -> None:
    # simple: cc 1, fully covered -> CRAP 1.
    # branchy: cc 3; lines 5-10 are executable and all but 9 ran -> coverage 5/6,
    # CRAP = 3^2 * (1/6)^3 + 3.
    executed = {1, 2, 5, 6, 7, 8, 10}
    missing = {9}
    simple, branchy = crap_scores("m.py", SOURCE, executed, missing)
    assert simple.crap == 1
    assert branchy.complexity == 3
    assert branchy.coverage == 5 / 6
    assert round(branchy.crap, 4) == round(9 * (1 / 6) ** 3 + 3, 4)
