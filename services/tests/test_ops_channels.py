"""Every channel the code logs to is one the ops_log table accepts. A rejected channel loses the log line, and when
the line reports a failure inside an except block, the failure itself is lost (provisioning, 2026-10-09)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALL = re.compile(r"\blog\((?:c|s|conn|scope), *\"([a-z_]+)\"")


def allowed() -> set[str]:
    sql = (ROOT / "services/api/schema.sql").read_text(encoding="utf-8")
    m = re.search(r"channel\s+text not null check \(channel in\s*\(([^)]*)\)", sql)
    assert m, "ops_log.channel check not found in schema.sql"
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def test_every_logged_channel_is_accepted_by_the_table():
    used = {}
    for f in list((ROOT / "services").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        if "tests" in f.parts:
            continue
        for ch in CALL.findall(f.read_text(encoding="utf-8")):
            used.setdefault(ch, []).append(str(f.relative_to(ROOT)))
    bad = {ch: files for ch, files in used.items() if ch not in allowed()}
    assert not bad, f"channels the ops_log check rejects: {bad}"
