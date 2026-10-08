"""An `async def` route runs ON the event loop: a blocking database or chain call inside it stalls every other
request in flight (the console polls /status every 5 s, so one blocking call there slowed every page). Blocking work
in an async route must go through run_in_threadpool. Static check, like test_tenancy_static."""
import ast
from pathlib import Path

ROUTES = Path(__file__).resolve().parent.parent / "api" / "routes"


def _calls_inside_threadpool(fn: ast.AsyncFunctionDef) -> set[int]:
    ids = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "run_in_threadpool":
            for sub in ast.walk(node):
                ids.add(id(sub))
    return ids


def test_async_routes_never_block_the_event_loop():
    offenders = []
    for f in sorted(ROUTES.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]:
            wrapped = _calls_inside_threadpool(fn)
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and id(node) not in wrapped:
                    src = ast.unparse(node.func)
                    if src.startswith(("repo_", "repo.", "ledger.")) or src == "report":
                        offenders.append(f"{f.name}:{node.lineno} {fn.name}: {src}(...)")
    assert not offenders, "blocking calls in async routes:\n" + "\n".join(offenders)
