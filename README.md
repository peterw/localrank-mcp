# LocalRank MCP Server

MCP server for Claude Desktop integration with LocalRank.

## Installation

```bash
uvx --from git+https://github.com/peterw/localrank-mcp localrank-mcp
```

## Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

## Available Tools

- `list_scans` - List all rank tracking scans
- `get_scan` - Get detailed ranking data for a specific scan
- `list_citations` - List all citations for your businesses
- `list_businesses` - List all businesses/locations being tracked
- `list_review_campaigns` - List all review collection campaigns
- `get_review_campaign` - Get details for a specific review campaign
- `list_gmb_locations` - List all connected Google My Business locations
- `list_gmb_reviews` - List reviews for a GMB location
