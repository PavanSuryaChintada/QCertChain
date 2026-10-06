"""The report must never state a number that was not measured."""
from scripts.evaluate import pct, section


def test_failed_section_is_unavailable_not_a_number():
    @section
    def broken():
        raise ConnectionError("crt.sh unreachable")
    out = broken()
    assert set(out) == {"unavailable", "trace"} and "crt.sh unreachable" in out["unavailable"]


def test_percentiles():
    assert pct([], .5) is None
    assert pct([1, 2, 3, 4, 5], .5) == 3 and pct([1, 2, 3, 4, 100], .95) == 100


def test_no_balanced_precision_anywhere():
    src = open("scripts/evaluate.py", encoding="utf-8").read()
    assert "balanced" not in src.replace("Balanced-set precision is never computed", "")
