"""QCertChain API — the only HTTP surface. Errors are RFC 7807 problem+json (API_CONTRACT.md)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.api.routes import campaigns, domains, email, evidence, ledger, ops, plans, stream
from services.ingest.triage import warm

PROBLEM = "application/problem+json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm()  # allowlist + brand matchers: never on the first request
    yield


app = FastAPI(title="QCertChain API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=[o for o in os.environ.get("CONSOLE_ORIGINS", "http://localhost:5173").split(",") if o],
                   allow_methods=["*"], allow_headers=["*"])


def problem(status: int, title: str, detail: str | None, instance: str) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": title, "status": status, "detail": detail,
                         "instance": instance}, status_code=status, media_type=PROBLEM)


@app.exception_handler(HTTPException)
async def http_problem(request: Request, exc: HTTPException):
    titles = {404: "Not found", 409: "Conflict", 413: "Payload too large", 422: "Unprocessable", 429: "Too many requests",
              503: "Service unavailable"}
    return problem(exc.status_code, titles.get(exc.status_code, "Error"), str(exc.detail), request.url.path)


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError):
    detail = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return problem(422, "Unprocessable", detail, request.url.path)


@app.get("/health")
def health():
    return {"status": "ok", "service": "qcertchain-api"}


for r in (stream.router, domains.router, campaigns.router, plans.router, evidence.router, ledger.router,
          email.router, ops.router):
    app.include_router(r)
