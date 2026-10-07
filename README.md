# LocalRank MCP Server

Connect LocalRank to Claude AI for natural language access to your agency data.

Most tools are read-only. A few deliberately limited write tools start scans, build citations and manage client report links, each with hard safety rails.

## Quick Start

### Claude.ai (Web)
1. Go to [claude.ai/settings/connectors](https://claude.ai/settings/connectors)
2. Click "Add custom connector"
3. Name: `LOCALRANK`
4. URL: Get your URL with API key from [app.localrank.so/mcp](https://app.localrank.so/mcp)

### Claude Desktop
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "localrank": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/peterw/localrank-mcp", "localrank-mcp"],
      "env": {
        "LOCALRANK_API_KEY": "your-api-key",
        "LOCALRANK_API_URL": "https://api.localrank.so"
      }
    }
  }
}
```

---

## What You Can Ask Claude

### Daily Operations
- "What should I work on today?"
- "Which clients need attention?"
- "Show me quick wins I can get this week"

### Client Management
- "How is Acme Plumbing doing?"
- "Generate a monthly report for Acme Plumbing"
- "Who's outranking my client?"
- "What should I recommend to help them rank better?"

### Scaling Your Agency
- "Give me a portfolio summary"
- "What tasks can I delegate to my VA?"
- "Which clients might churn?"
- "Show me my biggest wins for case studies"

### Sales & Renewals
- "Acme Plumbing is up for renewal - show me the value we delivered"
- "What content should Acme blog about?"
- "Draft a monthly update email for Acme"
- "Get every client's report link and a ready email for this month's send"

---

## CLI

The same package ships a `localrank` CLI for terminal use and coding agents
(Claude Code, Codex, Cursor). Every command prints JSON; errors go to stderr
as JSON with a non-zero exit code.

Node users can run it through the npm wrapper in `npm/` (auto-installs the
uv runtime on first use): `npx localrank ...` once published — see
`RELEASING.md`.

```bash
export LOCALRANK_API_KEY=lr_...   # create one at https://app.localrank.so/mcp

uvx --from git+https://github.com/peterw/localrank-mcp localrank auth
uvx --from git+https://github.com/peterw/localrank-mcp localrank businesses list
uvx --from git+https://github.com/peterw/localrank-mcp localrank scans list --limit 5
uvx --from git+https://github.com/peterw/localrank-mcp localrank scans get SCAN_ID
uvx --from git+https://github.com/peterw/localrank-mcp localrank scans run \
  --business-uuid UUID --keywords "plumber near me,emergency plumber" --test-mode
uvx --from git+https://github.com/peterw/localrank-mcp localrank citations list
uvx --from git+https://github.com/peterw/localrank-mcp localrank citations build \
  --name "Acme Plumbing" --address "123 Main St, Austin, TX" \
  --phone "512-555-0100" --website "https://acmeplumbing.com" --start --citations 50
```

`scans run` and `citations build` go through the same validation and
duplicate guardrails as the MCP write tools below.

---

## Available Tools

### 📊 Core Data
| Tool | Description |
|------|-------------|
| `list_scans` | List rank tracking scans. Filter by business_name. Includes visual map and PNG/JPG grid image URLs. |
| `get_scan` | Get ranking details with visual map URLs and keyword-level PNG/JPG grid image URLs. |
| `create_scan_run` | Limited scan write tool. Starts a scan with validation + duplicate guardrails. |
| `list_businesses` | List all clients being tracked |
| `list_citations` | List citations for businesses |
| `ensure_citation_business` | Very limited single-business citation write tool. Reuses an exact business match, creates a new business only when search is empty, and can optionally start a buildout with the requested citation count. |
| `ensure_citation_business_batch` | Batch version for multiple locations in one call (max 10 items). Each item still uses the same duplicate and buildout guardrails. |
| `list_review_campaigns` | List all review collection campaigns |
| `get_review_campaign` | Get campaign details and analytics |
| `list_gmb_locations` | List connected Google Business locations |
| `list_gmb_reviews` | List reviews for a GMB location |

### 📈 Client Reports
| Tool | Description |
|------|-------------|
| `client_report` | Compare recent scans - wins, drops, visual maps |
| `get_client_report_link` | The permanent client report URL for one business (turns it on if needed), with a ready email draft and the next scheduled scan. Same URL every time; it always shows the newest completed scan. |
| `list_client_report_links` | Read-only. Every business with a live client link: url, latest scan date, next scan date and a ready email draft. The whole monthly send in one call. |
| `disable_client_report_link` | Turn that link off. The old URL then says "This report is no longer available". |

### Permanent client report link

Put one URL in a recurring client email and never update it. The page needs no login and always shows the
business's newest completed scan, compared with the matching scan about a month earlier.

- `business` is a UUID from `list_businesses` or the exact business name. A name that matches more than one
  location, or none exactly, is rejected before anything changes, with the candidates listed.
- Calling `get_client_report_link` again returns the same URL. After `disable_client_report_link`, the next
  get makes a new URL.
- `get_client_report_link` and `disable_client_report_link` need an API key with write scope;
  `list_client_report_links` works with a read-only key.

### Monthly client send (LocalRank never sends the emails)

The agency, or its AI agent, sends the email from its own account. LocalRank only prepares it:

- `email_draft` is `{subject, body}`: a short, neutral email with this month's Top 3 coverage and average
  position (with the change since the matching scan about a month earlier), the permanent link, and the agency
  name as the sign-off. It never mentions LocalRank. Missing data or a missing comparison is said in words,
  never shown as 0. It is the same text the app's "Copy email for client" copies.
- `next_scan_date` is when the business is next scanned. `null` means no scan is scheduled (paused, cancelled or
  one-time only), so the link will keep showing the same scan. The tool message names those businesses.
- One call does the whole month: `list_client_report_links`, then send each `email_draft` from your own mail tool.

```json
{
  "count": 1,
  "links": [
    {
      "business": "Harbor Dental",
      "url": "https://app.localrank.so/share/report/871fa427-6bdb-46e0-9a66-3e1a594fc56a",
      "latest_scan_date": "2026-09-15T12:00:00Z",
      "next_scan_date": "2026-10-15T12:00:00Z",
      "email_draft": {
        "subject": "Harbor Dental: Google Maps ranking report, September 2026",
        "body": "Hi,\n\nHere is the latest Google Maps ranking report for Harbor Dental, from the scan on Sep 15, 2026.\n\n- Top 3 on Google Maps: 67% of the area we track (up from 33% on Aug 16, 2026)\n- Average position: 3.7 (improved from 7.7 on Aug 16, 2026)\n\nOpen the report here:\nhttps://app.localrank.so/share/report/871fa427-6bdb-46e0-9a66-3e1a594fc56a\n\nThis link stays the same and always shows the latest scan, so you can bookmark it.\n\nBest regards,\nAcme SEO"
      }
    }
  ],
  "message": "1 live client link(s). Each email_draft is a ready subject and body; LocalRank does not send it."
}
```

### Scan map-grid images

`list_scans` and `get_scan` include:

- `map_grid_image_png_url`
- `map_grid_image_jpg_url`
- `map_grid_image_auth`

Use the same `Authorization` header as the MCP/API request when fetching those image URLs, for example:

```bash
curl -H "Authorization: Api-Key YOUR_KEY" \
  "https://app.localrank.so/api/scans/SCAN_ID/map-grid-image?format=png"
```
| `get_ranking_changes` | All clients with ranking changes |
| `get_recommendations` | How to help a client rank better (suggests SuperBoost, LocalBoost, etc.) |
| `get_competitors` | Who's outranking your client per keyword |

### 💰 Agency Growth
| Tool | Description |
|------|-------------|
| `get_win_stories` | Biggest client wins for case studies |
| `get_at_risk_clients` | Clients who might churn |
| `renewal_pitch` | Value delivered since client started |
| `suggest_content` | Blog/content ideas from tracked keywords |
| `draft_client_email` | Auto-generate monthly update emails |

### ⚡ Scaling Operations
| Tool | Description |
|------|-------------|
| `portfolio_summary` | All clients at a glance |
| `prioritize_today` | What to work on right now |
| `find_quick_wins` | Keywords close to page 1 (rank 11-20) |
| `delegate_tasks` | Tasks for VA vs owner attention |

### Limited Citation Writes

`ensure_citation_business` is intentionally narrow:

- It requires exact `business_name`, `address`, `phone`, and `website`.
- It only creates a business when citation search returns zero candidates.
- If citation search returns near matches or multiple exact matches, it blocks and does nothing.
- It only starts buildout when `start_buildout=true`.
- It passes `requested_citations` through exactly as requested (no MCP-side cap).
- It blocks buildout for existing businesses that already have citations.
- First-location seed data is passed through only to help brand-new businesses start cleanly.

`ensure_citation_business_batch` is intentionally narrow too:

- Maximum 10 items per batch call.
- Each item still uses all `ensure_citation_business` guardrails.
- Optional `start_buildout` and `requested_citations` can be set once at the batch level as defaults.
- Optional `max_total_requested_citations` can cap requested buildout volume across the whole batch call.
- Invalid items fail closed and are returned as per-item errors without stopping valid items.

### Limited Scan Writes

`create_scan_run` is intentionally narrow:

- It requires `business_uuid` and `keywords` and validates payload shape before writing.
- It supports `scanType` (`one-time` default, `repeating` when frequency is provided).
- It checks recent active scans for the same business + keyword set + scan type.
- By default it blocks recent duplicates and fails closed with `blocked_recent_duplicate_scan`.
- It only allows duplicate retries when `allow_duplicate_recent=true` is explicitly provided.
- It emits a wide structured transaction log (`flow: mcp_tool_scan_run`) for auditability.

---

## Example Conversations

**Morning check-in:**
> "What should I focus on today?"

**Client call prep:**
> "Give me everything on Acme Plumbing - rankings, changes, what to recommend"

**Monthly reviews:**
> "Portfolio summary please"
> "Draft update emails for all clients with wins this month"

**Sales call:**
> "Show me my 3 biggest success stories"

**Renewal prep:**
> "Acme is up for renewal next week - build me a pitch"

**Very limited citation write:**
> "Create a citation business for Fresh HVAC at 99 Market St with phone 555-999-8888, website freshhvac.com, and start a tiny buildout"

**Very limited batch citation write:**
> "Use ensure_citation_business_batch for these 4 locations, start buildout, requested_citations 50, and max_total_requested_citations 120"

---

## Support

Questions? [support@localrank.so](mailto:support@localrank.so)
