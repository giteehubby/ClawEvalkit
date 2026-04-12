# Google Calendar

Access Google Calendar via the mock Calendar API server running at `http://127.0.0.1:8926`.

## Quick Start

```bash
# List events
python3 <<'EOF'
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8926/calendar/v3/calendars/primary/events?maxResults=50')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

## Endpoints

- **List events**: `GET http://127.0.0.1:8926/calendar/v3/calendars/primary/events?timeMin=...&timeMax=...`
- **Create event**: `POST http://127.0.0.1:8926/calendar/v3/calendars/primary/events`

## Scenario

Scenario data is loaded from `/app/mounts/google-calendar-api/scenario.json`.
