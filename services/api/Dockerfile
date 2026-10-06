# One image for the API and every worker (the command differs per service).
# bookworm pinned: Playwright 1.49 cannot install its deps on Debian trixie (python:3.11-slim since 2026)
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Python dependencies first (cached layer). The two local packages are installed from source.
COPY packages ./packages
COPY services/api/requirements.txt services/api/requirements-quantum.txt services/api/
RUN pip install -r services/api/requirements.txt -r services/api/requirements-quantum.txt

# Chromium for page confirmation; `install --with-deps` pulls the system libraries it needs.
RUN playwright install --with-deps chromium

COPY services ./services
COPY scripts ./scripts
COPY contracts/abi ./contracts/abi
COPY contracts/deployments ./contracts/deployments
COPY data/brands.yaml data/shared_hosting.txt data/brand_favicons.json ./data/

# The Tranco allowlist is regenerated at build time (100k rows, not committed).
RUN python -m scripts.fetch_allowlist

EXPOSE 8000
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
