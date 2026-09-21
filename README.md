# freelance-radar-mcp

[![test](https://github.com/Las-so/freelance-radar-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/Las-so/freelance-radar-mcp/actions/workflows/test.yml)

An [MCP](https://modelcontextprotocol.io) server that searches **official, public
job/freelance APIs** and, optionally, scores results against your own capability
keywords. No scraping, no unofficial endpoints, no shared or embedded credentials —
every call goes to a documented API, using your own key where a key is required.

Built as a small, finishable, real first rep: one legitimate authenticated-access
pattern, done end to end, with tests that hit the live API rather than mocks alone.

## Why this exists

Most "job board MCP" demos either scrape HTML (fragile, against most sites' terms)
or hardcode a single source. This one is deliberately architected around the
question *"what is the strongest legitimate, authenticated, programmable interface
available?"* for each source, and treats a missing credential as a clean, reported
skip — never a silent failure and never a workaround.

| Source | Auth | Status |
|---|---|---|
| [Remotive](https://remotive.com/api-documentation) | none — public API | always on |
| [Adzuna](https://developer.adzuna.com/) | `app_id` + `app_key` (free signup) | on when `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` are set |

Adding a third source (Indeed Publisher, USAJobs, Jooble, etc.) means writing one
more file in `src/freelance_radar_mcp/sources/` that returns the shared
`JobPosting` shape — the server and scorer don't change.

## Tools

- **`source_status()`** — which sources are live right now, and why. Call this
  first so you know exactly what you're querying.
- **`search_jobs(query, category, limit)`** — normalized postings from every
  configured source, fetched in parallel.
- **`score_opportunities(capability_keywords, query, category, limit)`** —
  `search_jobs` plus a transparent 0-100 relevance score (title matches count
  double). Output maps directly onto a `score` / `capability_match` style
  tracker column.

## Install

```bash
git clone https://github.com/Las-so/freelance-radar-mcp.git
cd freelance-radar-mcp
pip install -e ".[dev]"
```

## Run

```bash
# stdio MCP server — point your MCP client (Claude Desktop, etc.) at this command
freelance-radar-mcp

# or directly
python -m freelance_radar_mcp.server
```

### Optional: enable Adzuna

```bash
export ADZUNA_APP_ID="your_app_id"
export ADZUNA_APP_KEY="your_app_key"
```

Without these, `search_jobs` / `score_opportunities` still run — Adzuna is
reported in `sources_skipped` with the reason, Remotive results still come back.

### Claude Desktop config

```json
{
  "mcpServers": {
    "freelance-radar": {
      "command": "freelance-radar-mcp"
    }
  }
}
```

## Behind a TLS-intercepting proxy

`httpx` bundles its own CA store (via `certifi`) and, unlike `requests`, does
**not** automatically trust `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`. Behind a
proxy that injects its own root CA (sandboxed dev environments, some
corporate networks, CI runners), that mismatch fails every request with
`CERTIFICATE_VERIFY_FAILED` even though the proxy itself is fine.
`src/freelance_radar_mcp/http.py` checks those env vars and points `httpx`
at that CA bundle when present, so the same code runs unmodified on a bare
machine and behind a proxy. If you're launching this server as a subprocess
(as any MCP client does), remember the client also has to forward that env
var into the subprocess's environment — most MCP clients start servers with
a minimal environment for security, not your full shell env.

## Test

```bash
pip install -e ".[dev]"
pytest -v
```

`tests/test_live_remotive.py` makes a real network call to the live Remotive API
(no mocking) so a broken connector fails loudly instead of passing on stale mocks.
Everything else is a fast unit test against fixture data.

## License

MIT — see [LICENSE](LICENSE).
