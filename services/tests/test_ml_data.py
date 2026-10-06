"""MODELS.md §2: never a random split — same-campaign domains in train and test make AUC meaningless."""
from datetime import datetime, timedelta, timezone

from services.ml.datasets import campaign_key, dedupe_by_campaign
from services.ml.split import campaign_disjoint_split, temporal_split

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_campaign_key_collapses_numbered_variants():
    assert campaign_key("sbi-verify-01.top") == campaign_key("sbi-verify-400.top")
    assert campaign_key("sbi-verify-01.top") != campaign_key("hdfc-verify-01.top")
    assert campaign_key("a1b2.pages.dev") == campaign_key("a9b7.pages.dev")


def test_dedupe_by_campaign_keeps_one_per_key():
    rows = [{"etld1": f"sbi-verify-{i}.top", "seen": T0} for i in range(400)] + [{"etld1": "other.xyz", "seen": T0}]
    assert len(dedupe_by_campaign(rows)) == 2


def test_temporal_split_never_leaks_future_into_train():
    rows = [{"etld1": f"d{i}.top", "seen": T0 + timedelta(days=i)} for i in range(90)]
    train, test = temporal_split(rows, cutoff=T0 + timedelta(days=60))
    assert max(r["seen"] for r in train) < min(r["seen"] for r in test)
    assert len(train) == 60 and len(test) == 30


def test_campaign_disjoint_split_keeps_campaigns_whole():
    rows = [{"etld1": f"sbi-verify-{i}.top", "seen": T0} for i in range(50)] + \
           [{"etld1": f"hdfc-kyc-{i}.xyz", "seen": T0} for i in range(50)] + \
           [{"etld1": f"paytm-{i}.buzz", "seen": T0} for i in range(50)]
    train, test = campaign_disjoint_split(rows, test_fraction=0.34, seed=1)
    tk, sk = {campaign_key(r["etld1"]) for r in train}, {campaign_key(r["etld1"]) for r in test}
    assert tk and sk and not (tk & sk)
