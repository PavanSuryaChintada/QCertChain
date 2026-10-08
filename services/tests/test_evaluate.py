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


def test_confirmation_eval_covers_modern_js_kits(monkeypatch):
    """S3d: the labelled set must exercise the code that ships (JS-era kits), and report each family separately so a
    blind spot (same-origin relay) shows as a number instead of disappearing into an average."""
    import dataclasses

    from scripts import evaluate
    from services.enrich import confirm
    monkeypatch.setattr(confirm, "SETTINGS", dataclasses.replace(confirm.SETTINGS, exfil_signal_strength="strong",
                                                                 js_post_signal_strength="strong"))
    out = evaluate.confirmation()
    fam = out["by_family"]
    assert fam["modern_js_kit"]["n"] == 7 and fam["modern_js_legit"]["n"] == 2
    assert out["per_page"]["pJ0"] == "confirmed"           # Telegram exfil + a POST to a different site
    assert out["per_page"]["pJ5"] == "candidate"           # same-origin relay: invisible to any browser-side check
    assert out["per_page"]["pJ6"] == "candidate"           # one Telegram endpoint seen twice is one signal (S3b)
    assert out["false_confirmations_of_legit_pages"] == 0
