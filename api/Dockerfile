# Build context: repository root (the migration reads ../schema.sql).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv

WORKDIR /srv/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3.12

COPY schema.sql /srv/schema.sql
COPY api/ /srv/api/

ENV PATH=/opt/venv/bin:$PATH \
    SCHEMA_SQL=/srv/schema.sql \
    ASSET_DIR=/data/assets

RUN useradd --system --uid 10001 labelstudio && mkdir -p /data/assets && chown -R labelstudio /data
USER labelstudio

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# One worker: background tasks (imports, lease checks) live in-process; the scheduler also takes a PG
# advisory lock so a second replica would be safe.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
