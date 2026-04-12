# Google Search

Search the web using Google Custom Search API.

## Setup

Environment variables (set by the platform):
- `GOOGLE_API_KEY`: Your Google API key
- `GOOGLE_CSE_ID`: Your Custom Search Engine ID

## Quick Start

```bash
# Search using the built-in script
cd /root/skills/google-search/scripts
python3 search.py "your query" 5
```

## Scenario

Scenario data (for mock mode) is loaded from `/app/mounts/google-search/scenario.json`.

## Notes

If `web_search` tool is available, prefer using it for simpler searches.
