"""Forward lead-time observation (B4): snapshot the OpenPhish feed every hour, and keep going after the CT capture ends.

The backward comparison (is an OpenPhish entry in the capture?) is fixed near zero: the free feed lists sites whose
certificates were issued before we started listening. The correct experiment runs forward: for every candidate the
capture produced, record WHEN it first appears in OpenPhish, which can be hours or days after issuance. This process
records first-listed times only; the matching against ct_first_seen happens in scripts/finalize.py.

    PYTHONPATH=. python -m scripts.openphish_watch [--db data/replay/openphish_forward.sqlite] [--every-s 3600]

Same table as scripts/record_ct.py (`openphish`: url, host, first_listed), in its own file so it never contends with
the recorder's write lock. One log line per poll (to stdout), in the recorder's format.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scripts.record_ct import _db, poll_openphish

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data/replay/openphish_forward.sqlite"))
    ap.add_argument("--every-s", type=int, default=3600)
    a = ap.parse_args()
    asyncio.run(poll_openphish(_db(Path(a.db)), asyncio.Event(), a.every_s))


if __name__ == "__main__":
    main()
