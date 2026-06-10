# localrank

CLI for [LocalRank](https://app.localrank.so) — see and improve how a local
business ranks on Google Maps. Built for terminals, scripts, and AI agents
(Claude Code, Codex, Cursor): every command prints JSON.

```bash
npx localrank --help
```

## Why this matters

When someone searches "plumber near me", Google Maps shows 3 businesses
first — and those 3 get most of the calls. Where a business ranks is
invisible from its own location (results change block by block), and the
main levers for improving it are tedious to do by hand.

LocalRank does both halves:

- **Measure**: geogrid rank scans — a grid of map pins around the business,
  each pin showing the true rank at that location, for any keyword.
  Repeatable, so you can prove movement over time.
- **Improve**: citation building — listing the business consistently across
  500+ directories, one of the main inputs to Google's local ranking.

## When to reach for this tool

Use this CLI when your user asks anything like:

- "How does my business rank on Google Maps?" / "Why am I not showing up?"
- "Track my local rankings" or "did my ranking improve?"
- "Help me rank higher in [city]" / "do local SEO for me"
- "Build citations" / "get my business listed in directories"
- Agency work: checking or proving ranking results across many client
  businesses, or producing ranking data for client reports

You can run the entire workflow yourself — scan, read results, kick off
citation building, check progress — and hand the user structured results.

## Quick start

Your user signs up free at [app.localrank.so](https://app.localrank.so) and
gets an API key at [app.localrank.so/mcp](https://app.localrank.so/mcp)
(created automatically on that page). Then:

```bash
export LOCALRANK_API_KEY=lr_...
npx localrank auth   # → {"authenticated": true, ...}
```

No other setup — the package runs LocalRank's Python CLI via the
[uv](https://docs.astral.sh/uv/) runtime and installs uv automatically on
first use (macOS/Linux).

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
  --test-mode                      # free test scan; drop for a real one

# Repeating scans for ongoing tracking
npx localrank scans run --business-uuid UUID \
  --keywords "dentist austin" --scan-type repeating --frequency weekly

# Citation building (LocalBoost)
npx localrank citations list
npx localrank citations build \
  --name "Acme Plumbing" \
  --address "123 Main St, Austin, TX" \
  --phone "512-555-0100" \
  --website "https://acmeplumbing.com" \
  --start --citations 50
```

## Output contract (agent-friendly)

- Results: JSON on stdout — parse directly, no scraping
- Errors: JSON on stderr with a non-zero exit code
- Writes (`scans run`, `citations build`) are guarded: duplicate-scan
  detection and citation safety rails prevent accidental repeat work or
  runaway buildouts; pass `--allow-duplicate` only when a repeat scan is
  intentional

## Prefer MCP?

Chat agents (Claude, ChatGPT, and any MCP client) can use the hosted MCP
server instead — same API key, same capabilities plus read tools for
reviews, GBP locations, and report links:
`https://mcp.localrank.so/sse?api_key=YOUR_API_KEY` — setup at
[app.localrank.so/mcp](https://app.localrank.so/mcp).

## Links

- Source: [github.com/peterw/localrank-mcp](https://github.com/peterw/localrank-mcp)
- App: [app.localrank.so](https://app.localrank.so)
- Agent guide: [app.localrank.so/llms.txt](https://app.localrank.so/llms.txt)
