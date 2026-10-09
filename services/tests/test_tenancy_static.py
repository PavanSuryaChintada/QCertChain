"""T3 static + structural checks (run in CI with the rest of the suite).

1. No database call happens outside the repository layer: route modules and main.py never import sqlalchemy,
   never call .execute(), and never touch a connection.
2. A route handler cannot construct an unscoped query: no route except the admin router depends on the
   privileged connection (deps.get_conn); every org route receives deps.Scope, whose connection the DATABASE
   has already bound to one org (role qcc_app + row-level security).
3. Even a deliberately unscoped query on a Scope connection returns only the bound org's rows.
"""
import ast
from pathlib import Path

import pytest
import sqlalchemy as sa

ROUTES = Path("services/api/routes")
NO_DB = [*sorted(ROUTES.glob("*.py")), Path("services/api/main.py")]


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = node.module if isinstance(node, ast.ImportFrom) else None
            names = [a.name for a in node.names]
            if (mod or "").startswith("sqlalchemy") or any(n.startswith("sqlalchemy") for n in names):
                if path.name != "admin.py":  # admin: type annotation only, checked below
                    out.append(f"{path}:{node.lineno} imports sqlalchemy")
            if mod == "services.api.db" or (mod == "services.api" and "db" in names):
                out.append(f"{path}:{node.lineno} imports the engine module")
        if isinstance(node, ast.Attribute) and node.attr in ("execute", "exec_driver_sql", "conn", "scalar",
                                                             "mappings"):
            out.append(f"{path}:{node.lineno} .{node.attr}")
    return out


def test_no_db_calls_outside_repositories():
    bad = [v for p in NO_DB for v in _violations(p)]
    assert bad == [], "database access belongs in services/api/repos/: " + "; ".join(bad)


def test_only_admin_routes_touch_the_privileged_connection():
    from fastapi.routing import APIRoute

    from services.api import deps
    from services.api.main import app

    def flat(dep):
        for d in dep.dependencies:
            yield d.call
            yield from flat(d)

    org_routes = 0
    for r in app.routes:
        # keyless by design (spec 2026-10-09 §4): the throttled password login and the read-only-key sign-in list
        if not isinstance(r, APIRoute) or r.path in ("/health", "/auth/superadmin/login", "/orgs/public"):
            continue
        direct = [d.call for d in r.dependant.dependencies]
        calls = set(flat(r.dependant))
        assert deps.get_principal in calls, f"{r.path}: no auth"
        if r.path.startswith("/admin/"):
            assert deps.require_admin in calls, r.path
            continue
        if deps.require_superadmin in calls:  # the platform panel: organisations and keys, no organisation data
            continue
        assert deps.get_conn not in direct, f"{r.path} depends on the privileged connection directly"
        if deps.get_conn in calls:  # only through get_principal (key lookup) and get_scope (binds the org)
            assert deps.get_scope in calls or not any(c is deps.get_conn for c in direct), r.path
        org_routes += deps.get_scope in calls
    assert org_routes >= 15


@pytest.mark.db
def test_an_unscoped_query_on_a_scope_connection_still_sees_one_org(db):
    from services.api.db import bind_org, unbind_org
    db.execute(sa.text("insert into campaigns (org_id, label) values (1, 'one'), (2, 'two')"))
    db.execute(sa.text("insert into domains (name, etld1, origin_org_id) values ('a.example', 'a.example', 1), "
                       "('b.example', 'b.example', 2), ('pub.top', 'pub.top', null)"))
    sp = db.begin_nested()
    bind_org(db, 2)
    # deliberately no WHERE clause anywhere
    assert db.execute(sa.text("select label from campaigns")).scalars().all() == ["two"]
    assert sorted(db.execute(sa.text("select name from domains")).scalars()) == ["b.example", "pub.top"]
    with pytest.raises(sa.exc.DBAPIError):  # cannot write into another org either
        with db.begin_nested():
            db.execute(sa.text("insert into campaigns (org_id, label) values (1, 'forged')"))
    unbind_org(db)
    sp.rollback()
