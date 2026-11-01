from tools.dryer import Unit, duplicates, rank, shape

A = """
def total_price(items, tax):
    subtotal = 0
    for item in items:
        subtotal += item.price * item.count
    return round(subtotal * (1 + tax), 2)
"""
# Same code with other names and literals: a duplicate by hand.
B = """
def sum_weights(rows, factor):
    acc = 0
    for row in rows:
        acc += row.weight * row.n
    return round(acc * (1 + factor), 3)
"""
C = """
def greet(name):
    if not name:
        raise ValueError("no name")
    return f"Hello {name}"
"""


def test_names_and_literals_do_not_matter() -> None:
    assert shape(A) == shape(B)
    assert rank(Unit("a", shape(A)), Unit("b", shape(B))) == 1.0
    assert rank(Unit("a", shape(A)), Unit("c", shape(C))) < 0.5


def test_duplicates_respects_threshold_and_size() -> None:
    units = [Unit("a", shape(A)), Unit("b", shape(B)), Unit("c", shape(C))]
    assert [(round(r, 2), x.where, y.where) for r, x, y in duplicates(units, 0.8, 10)] == [
        (1.0, "a", "b")
    ]
    assert duplicates(units, 0.8, 1000) == []
