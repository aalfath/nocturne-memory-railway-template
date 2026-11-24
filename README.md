[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/nocturne-memory?utm_medium=integration&utm_source=button&utm_campaign=nocturne-memory)

# Nocturne Memory on Railway

One-click Railway template for [Nocturne Memory](https://github.com/Dataojitori/nocturne_memory) **2.5.6**, the long-term memory server for MCP agents (Claude Code, Codex, Cursor and others) with versioned, rollback-able memories and a web dashboard.

## What it deploys

| Service | Source | Purpose |
| --- | --- | --- |
| `Nocturne Memory` | this repo (`Dockerfile`) | MCP endpoints `/mcp` and `/sse`, REST API, web dashboard, health check `/health` |
| `Postgres` | Railway PostgreSQL | all memories, their history, and the app's settings and review changeset |

The Dockerfile downloads upstream commit `54c48ee` (tag `2.5.6`), checks its SHA-256, builds the dashboard with `node:22.23.5-trixie-slim@sha256:fbd104a1…` and runs the backend on `python:3.12.16-slim-trixie@sha256:37fc60d3…` under `tini`. `railway/railway_launcher.py`:

- waits for Postgres, writes upstream's `config.json` from the variables below, and runs the schema migrations under a Postgres advisory lock;
- keeps `config.json` and the review changeset in a `railway_app_files` table, so the app needs no volume;
- exits non-zero on any failure, so Railway's `ON_FAILURE` restart policy restarts it.

## Variables

| Variable | Value | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | private-network connection to Railway Postgres |
| `API_TOKEN` | `${{secret(48)}}` | generated; the dashboard and every MCP client need it (`Authorization: Bearer …`) |
| `PORT` | `8233` | port the app listens on |

Nothing needs to be filled in at deploy time.

## After deploy

1. Copy `API_TOKEN` from the `Nocturne Memory` service's Variables tab.
2. Open the service's public URL and paste the token into the dashboard.
3. Add the server to your MCP client:

```json
{
  "mcpServers": {
    "nocturne-memory": {
      "type": "http",
      "url": "https://YOUR-DOMAIN/mcp",
      "headers": { "Authorization": "Bearer YOUR-API-TOKEN" }
    }
  }
}
```

Use `/sse` for SSE-only clients, and `?namespace=NAME` for a separate memory space per agent.

## Resources

About 110 MB RSS on Railway after writing and reading memories, measured with a 0.5 GB / 1 vCPU limit, so it runs on Railway's Free plan.

## Updates

Merges to `main` here bump the pinned upstream release. Railway then shows an "update available" notice on every project deployed from the template, and you choose when to apply it. Read `CHANGELOG.md` first: breaking changes are listed at the top of each entry. Upstream now ships maintenance updates only (its authors point to their successor project, Horon).

## Licence

Nocturne Memory is MIT-licensed by its authors.
