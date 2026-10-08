"""QCertChain API — the only HTTP surface. Errors are RFC 7807 problem+json (API_CONTRACT.md)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from services.api.deps import get_principal, rate_limit, require_key_header
from services.api.timing import TimingMiddleware
from services.api.routes import admin, campaigns, domains, email, evidence, ledger, ops, plans, stream
from services.ingest.triage import warm

PROBLEM = "application/problem+json"


def _warm_solvers() -> None:
    """Load OR-Tools (first CP-SAT call measured 4.5 s cold vs 0.4 s warm) and start the QAOA worker process."""
    from interdict.solvers.cpsat import solve_cpsat
    from interdict.types import Problem
    solve_cpsat(Problem(("a",), {"d": frozenset({"a"})}, {"d": 1.0}, 1))
    try:
        from interdict.solvers import qaoa_isolated
        qaoa_isolated.warm()
    except Exception:  # Qiskit absent: QAOA falls back to CP-SAT by design
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading

    import interdict.router
    previous = interdict.router.ISOLATE_QAOA
    interdict.router.ISOLATE_QAOA = True  # QAOA must not compete for this process's GIL (34 s vs 9.8 s measured)
    warm()  # allowlist + brand matchers: never on the first request
    app.state.warmup = threading.Thread(target=_warm_solvers, daemon=True)  # tests join it before timing
    app.state.warmup.start()
    try:
        yield
    finally:
        interdict.router.ISOLATE_QAOA = previous
        from interdict.solvers import qaoa_isolated
        qaoa_isolated.shutdown()


# No public /docs or /openapi.json: every route except /health requires a key.
app = FastAPI(title="QCertChain API", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None,
              openapi_url=None)
app.add_middleware(TimingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)  # graph and list payloads compress ~5-10x
app.add_middleware(CORSMiddleware,
                   # both spellings of this machine: a demo opened at 127.0.0.1 must not fail on CORS
                   allow_origins=[o for o in os.environ.get(
                       "CONSOLE_ORIGINS", "http://localhost:5180,http://127.0.0.1:5180").split(",") if o],
                   allow_methods=["*"], allow_headers=["*"])


def problem(status: int, title: str, detail: str | None, instance: str) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail,
                         "instance": instance}, status_code=status, media_type=PROBLEM)


@app.exception_handler(HTTPException)
async def http_problem(request: Request, exc: HTTPException):
    titles = {401: "Unauthorized", 403: "Forbidden", 404: "Not found", 405: "Method not allowed", 409: "Conflict", 413: "Payload too large", 422: "Unprocessable", 429: "Too many requests",
              503: "Service unavailable"}
    resp = problem(exc.status_code, titles.get(exc.status_code, "Error"), str(exc.detail), request.url.path)
    for k, v in (exc.headers or {}).items():
        resp.headers[k] = v
    return resp


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError):
    detail = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return problem(422, "Unprocessable", detail, request.url.path)


@app.get("/health")
def health():
    """Unauthenticated by design: liveness, per-endpoint p95, and where the API and database run (no data)."""
    from services.api.health import report
    return report()


# Every router requires a valid key (401 otherwise). Org routers additionally take a Scope (deps.get_scope).
for r in (stream.router, domains.router, campaigns.router, plans.router, evidence.router, ledger.router,
          email.router, ops.router, admin.router):
    app.include_router(r, dependencies=[Depends(require_key_header), Depends(get_principal), Depends(rate_limit)])
