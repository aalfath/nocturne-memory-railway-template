# Changelog

## 2.5.6-railway.1 (2026-11-24)

First release.

- Nocturne Memory 2.5.6 (upstream commit `54c48ee`), built from source; dashboard built with Node 22.23.5, backend on Python 3.12.16 (both pinned by digest).
- One app service plus Railway Postgres. Settings and the review changeset are stored in Postgres, so the app needs no volume.
- Generated 48-character `API_TOKEN` protects the dashboard, REST API and MCP endpoints.
- Migrations run under a Postgres advisory lock; the launcher exits non-zero on failure so Railway restarts it.
- `pg_dump` is not installed: before a schema migration upstream saves a JSON export of the data instead of a SQL dump.
