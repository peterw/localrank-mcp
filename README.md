# LocalRank MCP Server

Connect LocalRank to Claude AI for natural language access to your agency data.

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

---

## Available Tools

### 📊 Core Data
| Tool | Description |
|------|-------------|
| `list_scans` | List rank tracking scans. Filter by business_name. |
| `get_scan` | Get ranking details with visual map URLs |
| `list_businesses` | List all clients being tracked |
| `list_citations` | List citations for businesses |
| `list_review_campaigns` | List all review collection campaigns |
| `get_review_campaign` | Get campaign details and analytics |
| `list_gmb_locations` | List connected Google Business locations |
| `list_gmb_reviews` | List reviews for a GMB location |

### 📈 Client Reports
| Tool | Description |
|------|-------------|
| `client_report` | Compare recent scans - wins, drops, visual maps |
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

---

## Support

Questions? [support@localrank.so](mailto:support@localrank.so)
