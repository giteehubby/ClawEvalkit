#!/usr/bin/env python3
"""
ZClawBench Mock HTTP Servers.

在容器中启动轻量级 mock HTTP 服务器，模拟 Gmail / Google Calendar / Google Search 等服务。
所有 mock servers 读取 scenario.json 文件来获取任务相关的 mock 数据。

用法:
    python3 /app/mock_servers.py --gmail-scenario /app/mounts/gmail/scenario.json \\
                                  --calendar-scenario /app/mounts/google-calendar-api/scenario.json \\
                                  --search-scenario /app/mounts/google-search/scenario.json \\
                                  --port-guard /tmp/mock_servers_ready
"""
import argparse
import base64
import json
import os
import re
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


# ---------------------------------------------------------------------------
# Gmail Mock Server (port 8924)
# ---------------------------------------------------------------------------

def _build_gmail_response(scenario_data: Dict[str, Any], path: str, query: Dict) -> Dict:
    """根据 Gmail API path 生成 mock 响应"""
    messages = scenario_data.get("initial_state", {}).get("messages", [])
    accounts = scenario_data.get("accounts", [{"id": "me", "email": "[REDACTED_EMAIL]"}])

    # /gmail/v1/users/me/messages
    if re.match(r"/gmail/v1/users/me/messages$", path):
        q = query.get("q", [""])[0].lower()
        label = query.get("label", [None])[0]

        filtered = messages
        if q:
            filtered = [
                m for m in messages
                if q in m.get("subject", "").lower()
                or q in m.get("body_text", "").lower()
                or q in m.get("from", "").lower()
            ]
        if label:
            filtered = [m for m in filtered if label in m.get("label_ids", [])]

        return {
            "messages": [
                {"id": m["id"], "threadId": m["thread_id"]} for m in filtered
            ],
            "nextPageToken": None,
            "resultSizeEstimate": len(filtered),
        }

    # /gmail/v1/users/me/messages/{id}
    m = re.match(r"/gmail/v1/users/me/messages/([^/]+)$", path)
    if m:
        msg_id = m.group(1)
        for msg in messages:
            if msg["id"] == msg_id:
                body_b64 = base64.urlsafe_b64encode(
                    msg.get("body_text", "").encode("utf-8")
                ).decode("ascii")
                return {
                    "id": msg["id"],
                    "threadId": msg["thread_id"],
                    "labelIds": msg.get("label_ids", ["INBOX"]),
                    "snippet": msg.get("snippet", ""),
                    "internalDate": str(
                        int(
                            Path().stat().st_mtime * 1000
                            if not msg.get("created_at")
                            else 0
                        )
                    ),
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "From", "value": msg.get("from", "")},
                            {"name": "To", "value": ", ".join(msg.get("to", []))},
                            {"name": "Subject", "value": msg.get("subject", "")},
                            {
                                "name": "Date",
                                "value": msg.get("created_at", ""),
                            },
                        ],
                        "body": {"size": len(msg.get("body_text", "")), "data": body_b64},
                    },
                    "attachments": msg.get("attachments", []),
                }
        return {"error": "Message not found", "id": msg_id}

    # /gmail/v1/users/me/messages/send
    if path == "/gmail/v1/users/me/messages/send":
        import time
        new_id = f"msg-{(int(time.time()*1000)%1000000):06d}"
        return {
            "id": new_id,
            "threadId": new_id,
            "labelIds": ["SENT"],
        }

    return {"error": "Unknown Gmail endpoint", "path": path}


class GmailHandler(BaseHTTPRequestHandler):
    """Gmail API mock handler"""

    def log_message(self, format, *args):
        pass  # silence logging

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/gmail/"):
            try:
                resp = _build_gmail_response(self.server.scenario_data, path, query)
                self._send_json(resp)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/gmail/"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            try:
                body_data = json.loads(body)
            except Exception:
                body_data = {}

            if path == "/gmail/v1/users/me/messages/send":
                resp = _build_gmail_response(self.server.scenario_data, path, {})
                # Include sent content in state if possible
                if hasattr(self.server, "scenario_data"):
                    new_msg = {
                        "id": resp.get("id", "msg-new"),
                        "threadId": resp.get("threadId", "thr-new"),
                        "mailbox": "SENT",
                        "label_ids": ["SENT"],
                        "from": self.server.scenario_data.get("accounts", [{}])[0].get("email", "[REDACTED_EMAIL]"),
                        "to": [body_data.get("to", "")],
                        "subject": body_data.get("subject", ""),
                        "body_text": body_data.get("body", ""),
                    }
                    # Update scenario data in memory
                    if "messages" not in self.server.scenario_data.get("initial_state", {}):
                        self.server.scenario_data.setdefault("initial_state", {})["messages"] = []
                    self.server.scenario_data["initial_state"]["messages"].append(new_msg)
                self._send_json(resp)
            else:
                self._send_json({"error": "Unknown POST endpoint"}, status=404)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def _send_json(self, data: Dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def run_gmail_mock(port: int, scenario_file: Optional[str]):
    """Run Gmail mock HTTP server"""
    server = HTTPServer(("127.0.0.1", port), GmailHandler)
    if scenario_file and Path(scenario_file).exists():
        with open(scenario_file) as f:
            server.scenario_data = json.load(f)
    else:
        # Fallback minimal scenario
        server.scenario_data = {
            "name": "default",
            "accounts": [{"id": "me", "email": "[REDACTED_EMAIL]"}],
            "initial_state": {"messages": []},
        }
    print(f"[Gmail mock] running on port {port}")
    server.serve_forever()


# ---------------------------------------------------------------------------
# Google Calendar Mock Server (port 8926)
# ---------------------------------------------------------------------------

def _build_calendar_response(scenario_data: Dict[str, Any], path: str, query: Dict) -> Dict:
    """根据 Calendar API path 生成 mock 响应"""
    calendars = scenario_data.get("calendars", [])
    operations = scenario_data.get("operations", {})
    primary_cal = next((c for c in calendars if c.get("primary") or c.get("id") == "primary"), calendars[0] if calendars else {})
    events = primary_cal.get("events", [])

    # GET /calendar/v3/calendars/primary/events
    if re.match(r"/calendar/v3/calendars/[^/]+/events$", path):
        time_min = query.get("timeMin", [None])[0]
        time_max = query.get("timeMax", [None])[0]
        max_results = int(query.get("maxResults", ["100"])[0])
        single_events = query.get("singleEvents", ["true"])[0] == "true"
        order_by = query.get("orderBy", ["startTime"])[0]

        filtered = events
        return {
            "kind": "calendar#events",
            "etag": f'"{primary_cal.get("summary","primary")}-etag"',
            "summary": primary_cal.get("summary", "Primary"),
            "updated": "2026-03-15T00:00:00.000Z",
            "timeZone": primary_cal.get("timeZone", "Asia/Shanghai"),
            "items": [
                {
                    "id": e["id"],
                    "summary": e.get("summary", ""),
                    "description": e.get("description", ""),
                    "start": e.get("start", {}),
                    "end": e.get("end", {}),
                    "attendees": e.get("attendees", []),
                    "kind": "calendar#event",
                    "etag": f'"{e["id"]}-etag"',
                    "status": "confirmed",
                    "location": e.get("location", ""),
                    "creator": {
                        "email": primary_cal.get("summary", "[REDACTED_EMAIL]"),
                        "self": True,
                    },
                    "organizer": {
                        "email": "primary",
                        "self": True,
                    },
                }
                for e in filtered[:max_results]
            ],
        }

    # POST /calendar/v3/calendars/primary/events (create event)
    if path.startswith("/calendar/v3/calendars/") and path.endswith("/events") and hasattr(_build_calendar_response, "_post"):
        pass  # handled in do_POST

    return {"error": "Unknown Calendar endpoint"}


class CalendarHandler(BaseHTTPRequestHandler):
    """Google Calendar API mock handler"""

    def log_message(self, format, *args):
        pass

    def _get_events(self):
        calendars = self.server.scenario_data.get("calendars", [])
        primary_cal = next(
            (c for c in calendars if c.get("primary") or c.get("id") == "primary"),
            calendars[0] if calendars else {},
        )
        return primary_cal.get("events", []), primary_cal

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/calendar/v3/"):
            try:
                events, primary_cal = self._get_events()

                # GET /calendar/v3/calendars/primary/events
                if re.match(r"/calendar/v3/calendars/[^/]+/events$", path):
                    time_min = query.get("timeMin", [None])[0]
                    time_max = query.get("timeMax", [None])[0]
                    max_results = int(query.get("maxResults", ["100"])[0])

                    filtered = events
                    resp = {
                        "kind": "calendar#events",
                        "etag": f'"{primary_cal.get("summary","primary")}-etag"',
                        "summary": primary_cal.get("summary", "Primary"),
                        "updated": "2026-03-15T00:00:00.000Z",
                        "timeZone": primary_cal.get("timeZone", "Asia/Shanghai"),
                        "items": [
                            {
                                "id": e["id"],
                                "summary": e.get("summary", ""),
                                "description": e.get("description", ""),
                                "start": e.get("start", {}),
                                "end": e.get("end", {}),
                                "attendees": e.get("attendees", []),
                                "kind": "calendar#event",
                                "etag": f'"{e["id"]}-etag"',
                                "status": "confirmed",
                                "location": e.get("location", ""),
                                "creator": {
                                    "email": "[REDACTED_EMAIL]",
                                    "self": True,
                                },
                                "organizer": {"email": "primary", "self": True},
                            }
                            for e in filtered[:max_results]
                        ],
                    }
                    self._send_json(resp)
                    return

                self._send_json({"error": "Not found"}, status=404)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/calendar/v3/calendars/") and path.endswith("/events"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            try:
                event_data = json.loads(body)
            except Exception:
                event_data = {}

            import time
            new_id = f"evt-{(int(time.time()*1000)%1000000):06d}"
            resp = {
                "summary": event_data.get("summary", ""),
                "description": event_data.get("description", ""),
                "start": event_data.get("start", {}),
                "end": event_data.get("end", {}),
                "attendees": event_data.get("attendees", []),
                "id": new_id,
                "hangoutLink": f"https://meet.google.com/new-meeting-{new_id}",
                "kind": "calendar#event",
                "etag": f'"{new_id}-etag"',
                "status": "confirmed",
                "htmlLink": f"https://calendar.google.com/calendar/event?eid={new_id}",
                "created": "2026-03-15T00:00:00.000Z",
                "updated": "2026-03-15T00:00:00.000Z",
                "location": event_data.get("location", ""),
                "creator": {"email": "[REDACTED_EMAIL]", "self": True},
                "organizer": {"email": "primary", "self": True},
            }
            self._send_json(resp)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def _send_json(self, data: Dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def run_calendar_mock(port: int, scenario_file: Optional[str]):
    """Run Google Calendar mock HTTP server"""
    server = HTTPServer(("127.0.0.1", port), CalendarHandler)
    if scenario_file and Path(scenario_file).exists():
        with open(scenario_file) as f:
            server.scenario_data = json.load(f)
    else:
        server.scenario_data = {
            "name": "default",
            "user": {"email": "[REDACTED_EMAIL]", "displayName": "User", "timeZone": "Asia/Shanghai"},
            "calendars": [{"id": "primary", "summary": "Primary", "timeZone": "Asia/Shanghai", "primary": True, "events": []}],
        }
    print(f"[Calendar mock] running on port {port}")
    server.serve_forever()


# ---------------------------------------------------------------------------
# Google Search Mock (scenario file only, no HTTP server needed)
# The agent uses web_search tool for Brave Search; this mock is for scripts
# ---------------------------------------------------------------------------

def build_search_response(scenario_data: Dict[str, Any], query: str) -> Dict:
    """Build Google Search mock response from scenario data"""
    responses = scenario_data.get("responses", {})
    query_lower = query.lower()

    # Try exact match first
    if query in responses:
        return responses[query]

    # Try case-insensitive match
    for key, val in responses.items():
        if key.lower() == query_lower:
            return val

    # Try partial match
    for key, val in responses.items():
        if query_lower in key.lower() or key.lower() in query_lower:
            return val

    # Fallback with wildcard
    if "*" in responses:
        return responses["*"]

    # No data found - return minimal empty response
    return {
        "responses": {
            query: {
                "searchTime": 0.01,
                "items": [
                    {
                        "title": f"No data for: {query}",
                        "link": "https://example.com",
                        "snippet": "No mock data available for this query.",
                    }
                ]
            }
        }
    }


# ---------------------------------------------------------------------------
# YouTube Transcript Mock (scripts/fetch_transcript.py)
# ---------------------------------------------------------------------------

YOUTUBE_TRANSCRIPT_TEMPLATE = '''
#!/usr/bin/env python3
"""Mock YouTube transcript fetcher - reads from scenario file"""
import sys, json, os
from pathlib import Path

SCENARIO_FILE = os.environ.get("YOUTUBE_TRANSCRIPT_SCENARIO_FILE", "/app/mounts/youtube-transcript/scenario.json")

def get_transcript(video_id_or_url):
    """Get transcript for a video from scenario data"""
    if not Path(SCENARIO_FILE).exists():
        return {{"error": "No scenario file found"}}

    with open(SCENARIO_FILE) as f:
        data = json.load(f)

    videos = data.get("videos", {{}})
    # Match by video ID or URL
    for vid_id, vid_data in videos.items():
        if vid_id == video_id_or_url or vid_data.get("url", "").endswith(video_id_or_url):
            return vid_data
        # Also check if video_id_or_url is in the URL
        if video_id_or_url in vid_data.get("url", ""):
            return vid_data

    return {{"error": f"Video not found: {{video_id_or_url}}"}}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fetch_transcript.py <video_url_or_id>", file=sys.stderr)
        sys.exit(1)

    video_arg = sys.argv[1]
    result = get_transcript(video_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''


# ---------------------------------------------------------------------------
# Main launcher
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ZClawBench Mock Servers Launcher")
    parser.add_argument("--gmail-port", type=int, default=8924)
    parser.add_argument("--gmail-scenario")
    parser.add_argument("--calendar-port", type=int, default=8926)
    parser.add_argument("--calendar-scenario")
    parser.add_argument("--search-scenario")
    parser.add_argument("--port-guard", default="/tmp/mock_servers_ready")
    args = parser.parse_args()

    threads = []

    # Gmail mock
    t = threading.Thread(
        target=run_gmail_mock,
        args=(args.gmail_port, args.gmail_scenario),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # Calendar mock
    t = threading.Thread(
        target=run_calendar_mock,
        args=(args.calendar_port, args.calendar_scenario),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # Write port guard file
    Path(args.port_guard).write_text(
        f"gmail={args.gmail_port}\\ncalendar={args.calendar_port}\\n"
    )

    print(f"[Mock servers] Gmail=:{args.gmail_port}, Calendar=:{args.calendar_port}")

    # Wait for interrupt
    try:
        signal.pause()
    except AttributeError:
        # macOS doesn't have signal.pause()
        import time
        while True:
            time.sleep(86400)


if __name__ == "__main__":
    main()
