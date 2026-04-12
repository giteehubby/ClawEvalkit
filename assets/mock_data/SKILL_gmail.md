# Gmail

Access Gmail via the mock Gmail API server running at `http://127.0.0.1:8924`.

## Quick Start

```bash
# List messages
python3 <<'EOF'
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8924/gmail/v1/users/me/messages?maxResults=10')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

## Endpoints

- **List messages**: `GET http://127.0.0.1:8924/gmail/v1/users/me/messages?q=keyword`
- **Get message**: `GET http://127.0.0.1:8924/gmail/v1/users/me/messages/{message_id}`
- **Send message**: `POST http://127.0.0.1:8924/gmail/v1/users/me/messages/send`

## Scenario

Scenario data is loaded from `/app/mounts/gmail/scenario.json`.
