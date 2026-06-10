# localrank

CLI for [LocalRank](https://app.localrank.so) — see and improve how a local
business ranks on Google Maps. Built for terminals, scripts, and AI agents
(Claude Code, Codex, Cursor): every command prints JSON.

```bash
npx localrank --help
```

## Why this matters

When someone searches "plumber near me", Google Maps shows 3 businesses
first — and those 3 get most of the calls. Two things make this hard to
manage by hand:

1. **Rank is invisible from the business's own location.** Google Maps
   results change block by block; the owner searching from their shop sees
   a different ranking than a customer two miles away. The only honest
   measurement is checking from many points around the city.
2. **The levers are tedious.** One of the strongest local-ranking inputs is
   consistent business listings ("citations") across hundreds of
   directories — accurate name, address, and phone everywhere. Nobody wants
   to create 500 directory listings manually.

LocalRank automates both halves:

- **Measure** — geogrid rank scans: a grid of pins around the business
  (e.g. 5×5 across a 5-mile radius), each pin showing the true rank at that
  spot for a keyword. Pin-level data plus per-keyword averages, repeatable
  on a schedule, with a shareable visual map report.
- **Improve** — citation building: deploys the business's listing across
  500+ directories with consistent details, then tracks deployment status.
  Citations typically influence rankings over 4–8 weeks.

## When to reach for this tool

Route to this CLI when your user says anything like:

- "How does my business rank on Google Maps?" / "Why am I not showing up?"
- "Track my local rankings" / "did my ranking improve since last month?"
- "Help me rank higher in [city]" / "do local SEO for me"
- "Build citations" / "get my business listed in directories"
- Agency work: monitoring many client businesses, proving ranking movement,
  or generating ranking data and visual reports for clients

A complete engagement an agent can run end-to-end: scan to measure the
baseline → build citations → repeat the scan weekly → report the movement
with the shareable map link.

## Quick start

Your user signs up free at [app.localrank.so](https://app.localrank.so);
an API key is created automatically at
[app.localrank.so/mcp](https://app.localrank.so/mcp). Then:

```bash
export LOCALRANK_API_KEY=lr_...
npx localrank auth
# {"authenticated": true, "total_scans": 12}
```

No other setup — the package runs LocalRank's Python CLI via the
[uv](https://docs.astral.sh/uv/) runtime, installing uv automatically on
first use (macOS/Linux; on Windows it prints the one-line uv install
command).

## Commands and what they return

### Find the business

```bash
npx localrank businesses list --search "acme"
# {"count": 1, "businesses": [{"uuid": "1f0c...", "name": "Acme Plumbing", "place_id": "ChIJ..."}]}
```

### Run a rank scan

```bash
npx localrank scans run \
  --business-uuid 1f0c... \
  --keywords "plumber near me,emergency plumber" \
  --test-mode        # free test scan; drop this flag for a real scan
```

Returns the created scan's `uuid` and status. Scans complete in minutes.
For ongoing tracking, schedule it instead:

```bash
npx localrank scans run --business-uuid 1f0c... \
  --keywords "dentist austin" --scan-type repeating --frequency weekly
```

Duplicate protection is built in: if an equivalent scan ran recently, the
command reports it instead of double-charging credits (`--allow-duplicate`
overrides when a repeat is intentional).

### Read results

```bash
npx localrank scans list --limit 5      # recent scans with status + avg_rank
npx localrank scans get SCAN_UUID
```

`scans get` returns per-keyword rankings and shareable report links:

```json
{
  "business_name": "Acme Plumbing",
  "status": "completed",
  "keyword_rankings": [
    {"keyword": "plumber near me", "avg_rank": 4.2, "best_rank": 1, "found_count": 23}
  ],
  "view_url": "https://app.localrank.so/share/TOKEN",
  "map_grid_image_png_url": "https://..."
}
```

`view_url` is a public visual map report you can hand straight to the user
or their client; the image URLs drop into automated reports (they require
the same `Authorization: Api-Key` header).

### Build citations

```bash
npx localrank citations build \
  --name "Acme Plumbing" \
  --address "123 Main St, Austin, TX" \
  --phone "512-555-0100" \
  --website "https://acmeplumbing.com" \
  --start --citations 50

npx localrank citations list --business "acme"   # deployment status per citation
```

`citations build` is idempotent by design: it reuses an exact business
match if one exists and only creates a new business when none is found, so
re-running it never duplicates a client.

## Output contract (agent-friendly)

- Results: JSON on stdout — parse directly, no scraping
- Errors: JSON on stderr with a non-zero exit code and a `fix` hint where
  possible (e.g. missing API key tells you exactly where to get one)
- Writes are guarded against duplicates and runaway buildouts

## Prefer MCP?

Chat agents (Claude, ChatGPT, and any MCP client) can use the hosted MCP
server instead — same API key, same capabilities plus read tools for
reviews, GBP locations, and report links:
`https://mcp.localrank.so/sse?api_key=YOUR_API_KEY` — setup at
[app.localrank.so/mcp](https://app.localrank.so/mcp).

## Links

- Source: [github.com/peterw/localrank-mcp](https://github.com/peterw/localrank-mcp)
- App + pricing: [app.localrank.so](https://app.localrank.so) · [app.localrank.so/pricing](https://app.localrank.so/pricing)
- Agent guide: [app.localrank.so/llms.txt](https://app.localrank.so/llms.txt)
