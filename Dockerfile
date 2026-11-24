# Nocturne Memory 2.5.6 for Railway: one service (MCP + REST API + web UI) + Railway Postgres.
# Upstream publishes no image, so we build from the pinned 2.5.6 tag (commit 54c48ee) and verify its checksum.
ARG NOCTURNE_COMMIT=54c48eeaeea3cca61ff6bc065cbe1a4c32a3b254
ARG NOCTURNE_SHA256=518cabfd6e3f0eafaf6e0d8046e19e71fe5891b6c4a008496ee950c59a6c912b

FROM python:3.12.16-slim-trixie@sha256:37fc60d303cb9294d3718b5b48998a0210bb1c73611c1399ef5eb7964c0536e5 AS src
ARG NOCTURNE_COMMIT
ARG NOCTURNE_SHA256
WORKDIR /src
RUN python -c "import hashlib,sys,tarfile,urllib.request;u='https://github.com/Dataojitori/nocturne_memory/archive/${NOCTURNE_COMMIT}.tar.gz';d=urllib.request.urlopen(u,timeout=120).read();h=hashlib.sha256(d).hexdigest();print('sha256',h);sys.exit(0 if h=='${NOCTURNE_SHA256}' else 'checksum mismatch');open('/tmp/s.tgz','wb').write(d);tarfile.open('/tmp/s.tgz').extractall('/src',filter='data')" \
 && mv /src/nocturne_memory-${NOCTURNE_COMMIT} /src/nocturne

FROM node:22.23.5-trixie-slim@sha256:fbd104a10cdcca7ab9fb59c10eaabbadde592dd8b3bd297038236aec621437ea AS ui
WORKDIR /ui
COPY --from=src /src/nocturne/frontend/ ./
RUN npm ci --no-audit --no-fund && npm run build

FROM python:3.12.16-slim-trixie@sha256:37fc60d303cb9294d3718b5b48998a0210bb1c73611c1399ef5eb7964c0536e5
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MALLOC_ARENA_MAX=2 \
    SNAPSHOT_DIR=/app/snapshots \
    PORT=8233
# pg_dump 18 from PGDG: upstream runs pg_dump before schema migrations and aborts if the client is older than the server.
COPY pgdg.asc /usr/share/keyrings/pgdg.asc
RUN echo "deb [signed-by=/usr/share/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 tini \
 && rm -r /var/lib/apt/lists/*
WORKDIR /app
COPY --from=src /src/nocturne/backend/requirements.txt /app/requirements.txt
COPY railway/constraints.txt /tmp/constraints.txt
RUN pip install -r /app/requirements.txt -c /tmp/constraints.txt \
 && rm /tmp/constraints.txt
COPY --from=src /src/nocturne/backend/ /app/
COPY --from=ui /ui/dist /frontend/dist
COPY railway/railway_launcher.py /app/railway_launcher.py
# upstream switches to its container layout (config.json in /app) when /.dockerenv exists
RUN touch /.dockerenv \
 && adduser --disabled-password --gecos '' --uid 10001 appuser \
 && mkdir -p /app/snapshots /app/backups \
 && chown -R appuser:appuser /app
USER appuser
EXPOSE 8233
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/app/railway_launcher.py"]
