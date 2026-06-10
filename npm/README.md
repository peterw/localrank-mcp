# localrank

CLI for [LocalRank](https://app.localrank.so) — Google Maps rank tracking and
citation building. Built for terminals, scripts, and AI coding agents
(Claude Code, Codex, Cursor): every command prints JSON.

```bash
npx localrank --help
```

No setup needed — the package runs LocalRank's Python CLI via the
[uv](https://docs.astral.sh/uv/) runtime and installs uv automatically on
first use (macOS/Linux).

## Auth

Create an API key at [app.localrank.so/mcp](https://app.localrank.so/mcp)
(free account), then:

```bash
export LOCALRANK_API_KEY=lr_...
npx localrank auth   # → {"authenticated": true, ...}
```

## Commands

```bash
# Businesses on the account
npx localrank businesses list --search "acme"

# Google Maps rank scans (geogrid)
npx localrank scans list --limit 5
npx localrank scans get SCAN_ID
npx localrank scans run \
  --business-uuid UUID \
  --keywords "plumber near me,emergency plumber" \
  --test-mode

# Citation building (LocalBoost)
npx localrank citations list
npx localrank citations build \
  --name "Acme Plumbing" \
  --address "123 Main St, Austin, TX" \
  --phone "512-555-0100" \
  --website "https://acmeplumbing.com" \
  --start --citations 50
```

## Output contract

- Results: JSON on stdout
- Errors: JSON on stderr, non-zero exit code
- Writes (`scans run`, `citations build`) are guarded against duplicates;
  pass `--allow-duplicate` to override the scan guardrail deliberately

## MCP server

Chat agents (Claude, ChatGPT, and any MCP client) can use the hosted MCP
server instead: `https://mcp.localrank.so/sse?api_key=YOUR_API_KEY` — same
API key, same tools. Setup instructions at
[app.localrank.so/mcp](https://app.localrank.so/mcp).

## Links

- Source: [github.com/peterw/localrank-mcp](https://github.com/peterw/localrank-mcp)
- App: [app.localrank.so](https://app.localrank.so)
- Agent guide: [app.localrank.so/llms.txt](https://app.localrank.so/llms.txt)
