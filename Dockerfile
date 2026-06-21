# Baskr backend image.
#
# Build context MUST be this directory (calhackathon2026/) because the app imports
# BOTH `app.*` (from baskr/backend) and `system_pieces.data_pipeline` (from here).
#
#   docker build -t baskr-backend .
#
# Runs the FastAPI app + the background two-stage consumer (started via the
# FastAPI lifespan in app/main.py) in a single process.

FROM python:3.12-slim AS base

# PyMuPDF ships self-contained manylinux wheels (MuPDF statically linked), so no
# system libGL/glib is needed; everything else is pure-Python or wheels too. That
# keeps the image slim and the build free of an apt mirror round-trip.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching. Three requirement sets:
#   - baskr backend runtime
#   - data_pipeline (requests, sentry-sdk)
#   - redis-agent-memory: optional Iris LTM SDK, imported lazily by app/agent_memory.py
COPY baskr/backend/requirements.txt /tmp/req-backend.txt
COPY system_pieces/data_pipeline/requirements.txt /tmp/req-pipeline.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/req-backend.txt -r /tmp/req-pipeline.txt \
    && pip install redis-agent-memory

# App code. Copy the two import roots into /app:
#   /app/baskr/backend/app   -> imported as `app.*`     (cwd = baskr/backend)
#   /app/system_pieces       -> imported as `system_pieces.*` (PYTHONPATH = /app)
COPY baskr/ /app/baskr/
COPY system_pieces/ /app/system_pieces/

# `app.*` resolves from cwd; `system_pieces.*` resolves from /app on PYTHONPATH.
ENV PYTHONPATH=/app
WORKDIR /app/baskr/backend

# Render (and most PaaS) inject $PORT; default to 8002 for local `docker run`.
ENV PORT=8002
EXPOSE 8002

# Exec form via sh -c so ${PORT} still expands at runtime (Render injects PORT).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
