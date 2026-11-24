"""Railway launcher for Nocturne Memory.

What it does before handing over to upstream's run_sse.py (same process):
  1. Checks DATABASE_URL and API_TOKEN (upstream needs >= 32 characters) and exits 1 if they are missing.
  2. Waits for Postgres (private DNS can take a minute on a first deploy).
  3. Restores config.json and the review/rollback changeset from Postgres, so the app needs no volume
     of its own (Railway's Free plan allows one volume per project, which Postgres uses).
  4. Writes config.json with the Railway settings (host 0.0.0.0, $PORT, token, database URL).
  5. Runs upstream's schema setup and migrations under a Postgres advisory lock and exits 1 if they fail
     (upstream's lifespan only logs the error and keeps serving without tables).
  6. Starts a background thread that copies config.json and snapshots/changeset.json back into Postgres
     every 2 seconds, then runs upstream's server. Any crash exits non-zero so Railway restarts it.
"""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

APP_DIR = Path("/app")
CONFIG_PATH = APP_DIR / "config.json"
SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "/app/snapshots"))
CHANGESET_PATH = SNAPSHOT_DIR / "changeset.json"
SYNC_FILES = {"config.json": CONFIG_PATH, "changeset.json": CHANGESET_PATH}
# Settings Railway controls; they are rewritten on every start and never stored in the database copy.
MANAGED_KEYS = ("database_url", "api_token", "host", "web_port", "auto_open_browser")
LOCK_KEY = 702115118  # arbitrary advisory-lock id for schema setup


def log(msg):
    print(f"[railway] {msg}", flush=True)


def die(msg):
    print(f"[railway] FATAL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def plain_pg_url(url):
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme == "postgres":
        scheme = "postgresql"
    if scheme != "postgresql":
        die("DATABASE_URL must be a PostgreSQL URL (postgresql://...)")
    return urlunsplit((scheme,) + tuple(parts[1:]))


def asyncpg_url(url):
    parts = urlsplit(url)
    return urlunsplit(("postgresql+asyncpg",) + tuple(parts[1:]))


def _ssl_for(dsn):
    """Same rule as upstream's DatabaseManager: TLS unless the host is local or the URL disables it."""
    from urllib.parse import parse_qs
    parts = urlsplit(dsn)
    qs = parse_qs(parts.query)
    values = qs.get("ssl", []) + qs.get("sslmode", [])
    if parts.hostname in ("localhost", "127.0.0.1", "::1"):
        return False
    if values and values[-1].lower() in ("disable", "false", "off", "0", "no"):
        return False
    return "prefer"


async def connect(dsn, timeout=10):
    import asyncpg
    parts = urlsplit(dsn)
    bare = urlunsplit(parts[:3] + ("", ""))
    return await asyncpg.connect(bare, timeout=timeout, ssl=_ssl_for(dsn))


async def wait_for_db(dsn, deadline_s=180):
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            conn = await connect(dsn)
            await conn.execute("SELECT 1")
            await conn.close()
            log(f"database reachable after {attempt} attempt(s)")
            return
        except Exception as e:  # noqa: BLE001
            if time.monotonic() - start > deadline_s:
                die(f"database not reachable after {deadline_s}s: {type(e).__name__}: {e}")
            if attempt == 1 or attempt % 10 == 0:
                log(f"waiting for database ({type(e).__name__})")
            await asyncio.sleep(2)


async def restore_files(dsn):
    conn = await connect(dsn)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS railway_app_files ("
            " name TEXT PRIMARY KEY, content TEXT NOT NULL,"
            " updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        rows = await conn.fetch("SELECT name, content FROM railway_app_files")
    finally:
        await conn.close()
    restored = {}
    for row in rows:
        path = SYNC_FILES.get(row["name"])
        if path is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(row["content"], encoding="utf-8")
        restored[row["name"]] = row["content"]
    log("restored from database: " + (", ".join(sorted(restored)) or "nothing (first boot)"))
    return restored


def write_config(db_url, token, port):
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except ValueError:
            log("stored config.json was unreadable; starting from defaults")
            cfg = {}
    if not cfg:
        # first boot: let upstream build its defaults from the environment
        import config as upstream_config
        cfg = upstream_config._build_cfg_from_kvs(dict(os.environ))
    cfg.update(
        {
            "database_url": db_url,
            "api_token": token,
            "host": "0.0.0.0",
            "web_port": port,
            "auto_open_browser": False,
        }
    )
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def init_schema(dsn):
    conn = await connect(dsn)
    try:
        waited = 0
        while not await conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY):
            if waited % 15 == 0:
                log("another deploy is setting up the schema; waiting")
            waited += 1
            if waited > 600:
                die("schema lock not released after 10 minutes")
            await asyncio.sleep(1)
        try:
            from db import get_db_manager, close_db
            await get_db_manager().init_db()
            await close_db()
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
    finally:
        await conn.close()


def _stored_text(name, path):
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if name == "config.json":
        try:
            cfg = json.loads(text)
        except ValueError:
            return None  # mid-write; try again next round
        for key in MANAGED_KEYS:
            cfg.pop(key, None)
        text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    return text


def sync_loop(dsn, last):
    """Copy changed files into Postgres every 2 s (Railway stops containers without a drain period)."""

    async def run():
        conn = None
        while True:
            try:
                if conn is None or conn.is_closed():
                    conn = await connect(dsn)
                for name, path in SYNC_FILES.items():
                    try:
                        text = _stored_text(name, path)
                    except OSError:
                        continue
                    if text == last.get(name):
                        continue
                    if text is None:
                        await conn.execute("DELETE FROM railway_app_files WHERE name=$1", name)
                    else:
                        await conn.execute(
                            "INSERT INTO railway_app_files(name, content) VALUES($1,$2) "
                            "ON CONFLICT (name) DO UPDATE SET content=EXCLUDED.content, updated_at=now()",
                            name,
                            text,
                        )
                    last[name] = text
            except Exception as e:  # noqa: BLE001
                log(f"state sync failed, will retry: {type(e).__name__}: {e}")
                conn = None
            await asyncio.sleep(2)

    asyncio.run(run())


def main():
    raw_url = os.environ.get("DATABASE_URL", "").strip()
    token = os.environ.get("API_TOKEN", "").strip()
    if not raw_url:
        die("DATABASE_URL is empty; reference the Postgres service, e.g. ${{Postgres.DATABASE_URL}}")
    if len(token) < 32:
        die("API_TOKEN must be at least 32 characters")
    try:
        port = int(os.environ.get("PORT") or "8233")
    except ValueError:
        die("PORT must be a number")

    dsn = plain_pg_url(raw_url)
    sys.path.insert(0, str(APP_DIR))
    os.chdir(APP_DIR)

    asyncio.run(wait_for_db(dsn))
    restored = asyncio.run(restore_files(dsn))
    write_config(asyncpg_url(dsn), token, port)
    asyncio.run(init_schema(dsn))
    log("schema ready")

    # Content restored from the database counts as already synced; anything new is copied on the first round.
    last = {
        "config.json": _stored_text("config.json", CONFIG_PATH) if "config.json" in restored else None,
        "changeset.json": restored.get("changeset.json"),
    }
    threading.Thread(target=sync_loop, args=(dsn, last), daemon=True, name="state-sync").start()

    import run_sse
    run_sse.main()
    # uvicorn returns only after a shutdown signal; anything else is a crash
    log("server stopped")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        die(f"unexpected error: {type(e).__name__}")
