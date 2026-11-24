# Deploy and Host Nocturne Memory on Railway

Nocturne Memory is an open-source (MIT) long-term memory server for AI agents that speak MCP, such as Claude Code, Codex, Cursor, Windsurf, Cline or Gemini CLI. Agents store memories under URIs like `core://project/notes`. Every change is versioned and can be reviewed or rolled back in a web dashboard.

## About Hosting Nocturne Memory

This template runs Nocturne Memory 2.5.6 as one service that serves the MCP endpoints (`/mcp` streamable HTTP and `/sse`), the REST API and the web dashboard on a Railway domain. A Railway PostgreSQL database stores every memory and its history. The app keeps its settings and review changeset in that database too, so it needs no volume of its own and survives redeploys and restarts. The service is locked by a generated API token (`API_TOKEN`, 48 characters). The dashboard asks for it and MCP clients send it as a Bearer header. Railway builds the service from a pinned upstream release, waits for Postgres, runs the schema migrations and checks `/health`. It needs about 120 MB of RAM, so it fits Railway's Free plan.

## Common Use Cases

* Give Claude Code, Codex, Cursor or any other MCP client one shared, persistent memory across sessions and machines
* Keep an agent's identity, preferences and project knowledge in structured, versioned memories you can review and roll back
* Run separate memory spaces for several agents on one server with the `namespace` URL parameter

## Dependencies for Nocturne Memory Hosting

* Nocturne Memory 2.5.6 (built from the upstream release tag)
* PostgreSQL (Railway's managed database)

### Deployment Dependencies

* Source: https://github.com/Dataojitori/nocturne_memory
* Template repo: https://github.com/aalfath/nocturne-memory-railway-template

### Implementation Details

**Services:** `Nocturne Memory` (MCP + REST API + dashboard, public, health check `/health`) and `Postgres` (all data, on a volume). Nothing to fill in at deploy time.

**After deploy:** open the `Nocturne Memory` service, copy `API_TOKEN` from its Variables tab, open the public URL and paste the token into the dashboard. Then add the server to your MCP client, for example in `.mcp.json` or `~/.claude.json`:

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

Clients that only support SSE use `https://YOUR-DOMAIN/sse`. Add `?namespace=NAME` to the URL to give an agent its own memory space. The agent gets seven tools: `read_memory`, `create_memory`, `update_memory`, `delete_memory`, `add_alias`, `manage_triggers` and `search_memory`.

**Updates:** when we publish a new upstream release, Railway shows an update notice on your project; the repo's `CHANGELOG.md` lists what changed. Upstream now ships maintenance updates only, and its authors point new users to their successor project, Horon.

**Left out:** upstream's nginx container (the app serves the dashboard itself behind Railway's proxy), the desktop pet and the demo database.

## Why Deploy Nocturne Memory on Railway?

<!-- Recommended: Keep this section as shown below -->
Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying Nocturne Memory on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
<!-- End recommended section -->
