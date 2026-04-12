"""
ZClawBench Mock Injection — 将原始 ZClawBench 平台的 mock service 注入机制
完整复制到 ClawEvalKit 的 Docker 容器中。

原始 ZClawBench 注入机制:
  1. /app/mock/              预安装的 mock 服务脚本（Python HTTP servers）
  2. /app/mounts/{skill}/scenario.json   每个 task 的 scenario 数据文件
  3. /home/user/skills/{skill}/SKILL.md  技能说明文档
  4. scripts/fetch_transcript.py          YouTube transcript 获取脚本
  5. 环境变量: GMAIL_MOCK_BASE_URL, GOOGLE_CALENDAR_MOCK_PORT 等

本模块将这些文件/服务注入到容器中，匹配原始 ZClawBench 的行为。
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 导入已提取的 scenario 数据
from . import zclawbench_mock_data


# ---------------------------------------------------------------------------
# Skill Markdown 内容（基于原始 ZClawBench reference trajectories）
# ---------------------------------------------------------------------------

SKILL_GMAIL = '''# Gmail

Access Gmail via the mock Gmail API server at `http://127.0.0.1:8924`.

## Quick Start

```bash
python3 <<'EOF'
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8924/gmail/v1/users/me/messages?maxResults=10')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

## Endpoints

- **List messages** (search by query):
  `GET http://127.0.0.1:8924/gmail/v1/users/me/messages?q=keyword&maxResults=10`
- **Get message by ID**:
  `GET http://127.0.0.1:8924/gmail/v1/users/me/messages/{message_id}`
- **Send message**:
  `POST http://127.0.0.1:8924/gmail/v1/users/me/messages/send`
  Body: `{"to": "recipient@example.com", "subject": "Subject", "body": "Text body"}`

The scenario data is at `/app/mounts/gmail/scenario.json`.
'''

SKILL_CALENDAR = '''# Google Calendar

Access Google Calendar via the mock Calendar API server at `http://127.0.0.1:8926`.

## Quick Start

```bash
python3 <<'EOF'
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8926/calendar/v3/calendars/primary/events?maxResults=50')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

## Endpoints

- **List events**:
  `GET http://127.0.0.1:8926/calendar/v3/calendars/primary/events?timeMin=...&timeMax=...`
- **Create event**:
  `POST http://127.0.0.1:8926/calendar/v3/calendars/primary/events`
  Body: `{"summary": "Event Title", "start": {"dateTime": "2026-03-18T10:00:00+08:00"}, "end": {"dateTime": "2026-03-18T11:00:00+08:00"}}`

The scenario data is at `/app/mounts/google-calendar-api/scenario.json`.
'''

SKILL_GOOGLE_SEARCH = '''# Google Search Skill

This skill provides web search via Google Custom Search API (mock mode).

## Quick Start

```bash
cd /root/skills/google-search/scripts
python3 search.py "your query" 5
```

## Notes

If the `web_search` tool is available in your agent, prefer using it.
Scenario mock data is at `/app/mounts/google-search/scenario.json`.
'''

SKILL_YOUTUBE = '''# YouTube Transcript

Get transcripts for YouTube videos using the transcript fetcher.

## Usage

```bash
python3 scripts/fetch_transcript.py <video_url_or_id>
python3 scripts/fetch_transcript.py https://www.youtube.com/watch?v=HNMedge2401
```

The scenario data is at `/app/mounts/youtube-transcript/scenario.json`.
'''


# ---------------------------------------------------------------------------
# Scenario name mapping: task_id -> scenario_name
# Based on environment variables found in reference trajectories
# ---------------------------------------------------------------------------

# Maps task_id -> Gmail scenario name
GMAIL_SCENARIO_MAP = {
    "zcb_023": "script-mode-0010",
    "zcb_025": "script-mode-0013",
    "zcb_028": "cb_022",
    "zcb_032": "script-mode-0018",
}

# Maps task_id -> Calendar scenario name
CALENDAR_SCENARIO_MAP = {
    "zcb_026": "script-mode-0014",
    "zcb_028": "cb_022",
    "zcb_033": "cb_033",
    "zcb_034": "cb_034",
}

# Maps task_id -> Search scenario name
SEARCH_SCENARIO_MAP = {
    "zcb_007": "cb_007",
    "zcb_008": "cb_008",
    "zcb_027": "cb_027",
    "zcb_028": "cb_028",
    "zcb_030": "cb_030",
    "zcb_032": "cb_032",
    "zcb_068": "script-mode-0016",
    "zcb_071": "cb_071",
}


def _load_mock_scenarios() -> tuple:
    """Load extracted mock scenarios from assets"""
    gmail_scenarios, calendar_scenarios, search_scenarios = zclawbench_mock_data.load_scenarios()
    return gmail_scenarios, calendar_scenarios, search_scenarios


def get_scenario_name(task_id: str, skill: str) -> Optional[str]:
    """Get scenario name for a task and skill type"""
    if skill == "gmail":
        return GMAIL_SCENARIO_MAP.get(task_id)
    elif skill == "calendar":
        return CALENDAR_SCENARIO_MAP.get(task_id)
    elif skill == "search":
        return SEARCH_SCENARIO_MAP.get(task_id)
    return None


# ---------------------------------------------------------------------------
# Mock Server Python Script (to be copied into container)
# ---------------------------------------------------------------------------

MOCK_SERVERS_SCRIPT = r'''#!/usr/bin/env python3
"""ZClawBench Mock HTTP Servers — runs inside Docker container"""
import argparse, base64, json, os, re, signal, sys, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _build_gmail_response(scenario_data, path, query):
    messages = scenario_data.get("initial_state", {}).get("messages", [])
    if path == "/gmail/v1/users/me/messages":
        q = query.get("q", [""])[0].lower()
        label = query.get("label", [None])[0]
        filtered = messages
        if q:
            filtered = [m for m in messages if q in m.get("subject","").lower() or q in m.get("body_text","").lower() or q in m.get("from","").lower()]
        if label:
            filtered = [m for m in filtered if label in m.get("label_ids", [])]
        return {"messages": [{"id": m["id"], "threadId": m["thread_id"]} for m in filtered], "nextPageToken": None, "resultSizeEstimate": len(filtered)}
    m = re.match(r"/gmail/v1/users/me/messages/([^/]+)$", path)
    if m:
        msg_id = m.group(1)
        for msg in messages:
            if msg["id"] == msg_id:
                body_b64 = base64.urlsafe_b64encode(msg.get("body_text","").encode("utf-8")).decode("ascii")
                return {"id": msg["id"], "threadId": msg["thread_id"], "labelIds": msg.get("label_ids",["INBOX"]), "snippet": msg.get("snippet",""), "internalDate": str(int(time.time()*1000)), "payload": {"mimeType": "text/plain", "headers": [{"name":"From","value":msg.get("from","")},{"name":"To","value":", ".join(msg.get("to",[]))},{"name":"Subject","value":msg.get("subject","")},{"name":"Date","value":msg.get("created_at","")}],"body":{"size":len(msg.get("body_text","")),"data":body_b64}},"attachments": msg.get("attachments",[])}
        return {"error": "Message not found", "id": msg_id}
    if path == "/gmail/v1/users/me/messages/send":
        new_id = "msg-{:06d}".format(int(time.time()*1000)%1000000)
        return {"id": new_id, "threadId": new_id, "labelIds": ["SENT"]}
    return {"error": "Unknown endpoint", "path": path}


class GmailHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/gmail/"):
            try:
                resp = _build_gmail_response(self.server.scenario_data, parsed.path, parse_qs(parsed.query))
                self._send_json(resp)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/gmail/v1/users/me/messages/send":
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl).decode("utf-8")) if cl > 0 else {}
            resp = {"id": "msg-{:06d}".format(int(time.time()*1000)%1000000), "threadId": "thr-new", "labelIds": ["SENT"]}
            self._send_json(resp)
        else:
            self._send_json({"error": "Not found"}, 404)
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


class CalendarHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def _events_and_cal(self):
        cals = self.server.scenario_data.get("calendars", [])
        cal = next((c for c in cals if c.get("primary") or c.get("id")=="primary"), cals[0] if cals else {})
        return cal.get("events", []), cal
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/calendar/v3/"):
            try:
                events, cal = self._events_and_cal()
                if re.match(r"/calendar/v3/calendars/[^/]+/events$", parsed.path):
                    q = parse_qs(parsed.query)
                    max_results = int(q.get("maxResults",["100"])[0])
                    resp = {"kind":"calendar#events","etag":'"etag"','"summary"':cal.get("summary","Primary"),"updated":"2026-03-15T00:00:00.000Z","timeZone":cal.get("timeZone","Asia/Shanghai"),"items":[{"id":e["id"],"summary":e.get("summary",""),"description":e.get("description",""),"start":e.get("start",{}),"end":e.get("end",{}),"attendees":e.get("attendees",[]),"kind":"calendar#event","etag":'"%s-etag"'%e["id"],"status":"confirmed","location":e.get("location",""),"creator":{"email":"[REDACTED_EMAIL]","self":True},"organizer":{"email":"primary","self":True}} for e in events[:max_results]]}
                    self._send_json(resp)
                    return
                self._send_json({"error": "Not found"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/calendar/v3/calendars/") and parsed.path.endswith("/events"):
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl).decode("utf-8")) if cl > 0 else {}
            new_id = "evt-{:06d}".format(int(time.time()*1000)%1000000)
            resp = {"summary":body.get("summary",""),"description":body.get("description",""),"start":body.get("start",{}),"end":body.get("end",{}),"attendees":body.get("attendees",[]),"id":new_id,"hangoutLink":"https://meet.google.com/new-meeting","kind":"calendar#event","etag":'"%s-etag"'%new_id,"status":"confirmed","htmlLink":"https://calendar.google.com/calendar/event?eid="+new_id,"created":"2026-03-15T00:00:00.000Z","updated":"2026-03-15T00:00:00.000Z","location":body.get("location",""),"creator":{"email":"[REDACTED_EMAIL]","self":True},"organizer":{"email":"primary","self":True}}
            self._send_json(resp)
        else:
            self._send_json({"error": "Not found"}, 404)
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def run_gmail(port, scenario_data):
    server = HTTPServer(("127.0.0.1", port), GmailHandler)
    server.scenario_data = scenario_data
    print(f"[Gmail mock] port {port}")
    server.serve_forever()


def run_calendar(port, scenario_data):
    server = HTTPServer(("127.0.0.1", port), CalendarHandler)
    server.scenario_data = scenario_data
    print(f"[Calendar mock] port {port}")
    server.serve_forever()


def main():
    import json as _json
    gmail_port = int(os.environ.get("GMAIL_MOCK_PORT", "8924"))
    cal_port = int(os.environ.get("GOOGLE_CALENDAR_MOCK_PORT", "8926"))
    gmail_scenario_file = os.environ.get("GMAIL_MOCK_SCENARIO_FILE", "/app/mounts/gmail/scenario.json")
    cal_scenario_file = os.environ.get("GOOGLE_CALENDAR_MOCK_SCENARIO_FILE", "/app/mounts/google-calendar-api/scenario.json")

    gmail_data = _json.loads(Path(gmail_scenario_file).read_text()) if Path(gmail_scenario_file).exists() else {"name":"default","accounts":[{"id":"me","email":"[REDACTED_EMAIL]"}],"initial_state":{"messages":[]}}
    cal_data = _json.loads(Path(cal_scenario_file).read_text()) if Path(cal_scenario_file).exists() else {"name":"default","calendars":[{"id":"primary","summary":"Primary","timeZone":"Asia/Shanghai","primary":True,"events":[]}]}

    t1 = threading.Thread(target=run_gmail, args=(gmail_port, gmail_data), daemon=True)
    t2 = threading.Thread(target=run_calendar, args=(cal_port, cal_data), daemon=True)
    t1.start(); t2.start()
    print("[Mock servers] started")
    signal.pause()


if __name__ == "__main__":
    main()
'''


def _build_minimal_gmail_scenario(task_id: str) -> dict:
    """Build minimal Gmail scenario for tasks without extracted data"""
    return {
        "name": task_id.replace("zcb_", "cb_"),
        "accounts": [{"id": "me", "email": "[REDACTED_EMAIL]", "display_name": "User"}],
        "initial_state": {"messages": [], "drafts": [], "threads": []},
        "operations": {"send_message": {"responses": []}},
    }


def _build_minimal_calendar_scenario(task_id: str) -> dict:
    """Build minimal Calendar scenario for tasks without extracted data"""
    return {
        "name": task_id.replace("zcb_", "cb_"),
        "user": {"email": "[REDACTED_EMAIL]", "displayName": "User", "timeZone": "Asia/Shanghai"},
        "calendars": [{"id": "primary", "summary": "Primary", "timeZone": "Asia/Shanghai", "primary": True, "events": []}],
        "operations": {"create_event": {"responses": []}},
    }


def _build_minimal_search_scenario(task_id: str) -> dict:
    """Build minimal Search scenario for tasks without extracted data"""
    return {
        "name": task_id.replace("zcb_", "cb_"),
        "responses": {
            "*": {
                "searchTime": 0.01,
                "items": [{"title": "No data", "link": "https://example.com", "snippet": "No mock data for this query."}],
            }
        },
    }


def prepare_mock_injection(
    task_id: str,
    gmail_scenarios: Dict[str, Any],
    calendar_scenarios: Dict[str, Any],
    search_scenarios: Dict[str, Any],
) -> dict:
    """Prepare mock injection config for a specific task.

    Returns dict with paths to scenario files and skill content.
    """
    gmail_scenario_name = GMAIL_SCENARIO_MAP.get(task_id)
    calendar_scenario_name = CALENDAR_SCENARIO_MAP.get(task_id)
    search_scenario_name = SEARCH_SCENARIO_MAP.get(task_id)

    # Get Gmail scenario
    gmail_data = None
    if gmail_scenario_name and gmail_scenario_name in gmail_scenarios:
        gmail_data = gmail_scenarios[gmail_scenario_name]
    elif gmail_scenario_name in gmail_scenarios:
        gmail_data = gmail_scenarios[gmail_scenario_name]
    else:
        gmail_data = _build_minimal_gmail_scenario(task_id)

    # Get Calendar scenario
    calendar_data = None
    if calendar_scenario_name and calendar_scenario_name in calendar_scenarios:
        calendar_data = calendar_scenarios[calendar_scenario_name]
    elif calendar_scenario_name in calendar_scenarios:
        calendar_data = calendar_scenarios[calendar_scenario_name]
    else:
        calendar_data = _build_minimal_calendar_scenario(task_id)

    # Get Search scenario
    search_data = None
    if search_scenario_name and search_scenario_name in search_scenarios:
        search_data = search_scenarios[search_scenario_name]
    elif search_scenario_name in search_scenarios:
        search_data = search_scenarios[search_scenario_name]
    else:
        search_data = _build_minimal_search_scenario(task_id)

    return {
        "task_id": task_id,
        "gmail": {"data": gmail_data, "name": gmail_scenario_name},
        "calendar": {"data": calendar_data, "name": calendar_scenario_name},
        "search": {"data": search_data, "name": search_scenario_name},
    }


def inject_mock_into_container(
    container_name: str,
    task_id: str,
    gmail_scenarios: Dict[str, Any],
    calendar_scenarios: Dict[str, Any],
    search_scenarios: Dict[str, Any],
    skill_files_dir: Path,
) -> None:
    """Inject mock services, scenario data, and skill files into the running container.

    1. Create /app/mounts/{skill}/ directory and scenario.json files
    2. Copy mock_servers.py to /tmp/
    3. Launch mock servers as background processes
    4. Create skill directories at /home/user/skills/
    5. Create scripts/ directory with fetch_transcript.py
    """
    injection = prepare_mock_injection(task_id, gmail_scenarios, calendar_scenarios, search_scenarios)

    # 1. Create mount directories and scenario files
    for skill, dirname in [("gmail", "gmail"), ("calendar", "google-calendar-api"), ("search", "google-search")]:
        mount_path = f"/app/mounts/{dirname}"
        scenario_file = f"{mount_path}/scenario.json"
        data = injection[skill]["data"]

        # Create directory in container
        subprocess.run(["docker", "exec", container_name, "mkdir", "-p", mount_path], check=True)
        # Write scenario file to container via temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_scenario = f.name
        try:
            subprocess.run(["docker", "cp", tmp_scenario, f"{container_name}:{scenario_file}"], check=True)
        finally:
            Path(tmp_scenario).unlink(missing_ok=True)

    # 2. Copy mock servers script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(MOCK_SERVERS_SCRIPT)
        tmp_script = f.name
    try:
        subprocess.run(["docker", "cp", tmp_script, f"{container_name}:/tmp/mock_servers.py"], check=True)
    finally:
        Path(tmp_script).unlink(missing_ok=True)

    # 3. Create /home/user/skills/ directory and copy skill files
    skills_base = "/home/user/skills"
    subprocess.run(["docker", "exec", container_name, "mkdir", "-p", skills_base], check=True)

    # Copy SKILL.md files
    for skill_name, skill_md in [
        ("gmail", SKILL_GMAIL),
        ("google-calendar-api", SKILL_CALENDAR),
        ("google-search", SKILL_GOOGLE_SEARCH),
        ("youtube-transcript", SKILL_YOUTUBE),
    ]:
        skill_dir = f"{skills_base}/{skill_name}"
        subprocess.run(["docker", "exec", container_name, "mkdir", "-p", skill_dir], check=True)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(skill_md)
            tmp_md = f.name
        try:
            subprocess.run(["docker", "cp", tmp_md, f"{container_name}:{skill_dir}/SKILL.md"], check=True)
        finally:
            Path(tmp_md).unlink(missing_ok=True)

    # 4. Copy fetch_transcript.py to /tmp/scripts/
    scripts_dir_in_container = "/tmp/scripts"
    subprocess.run(["docker", "exec", container_name, "mkdir", "-p", scripts_dir_in_container], check=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(Path(skill_files_dir / "fetch_transcript.py").read_text())
        tmp_transcript = f.name
    try:
        subprocess.run(["docker", "cp", tmp_transcript, f"{container_name}:{scripts_dir_in_container}/fetch_transcript.py"], check=True)
    finally:
        Path(tmp_transcript).unlink(missing_ok=True)

    # 5. Launch mock servers in background
    # Use nohup to run in background, redirect output
    launch_cmd = [
        "docker", "exec", container_name,
        "sh", "-c",
        "cd /tmp && nohup python3 mock_servers.py > /tmp/mock_servers.log 2>&1 & "
        "echo $! > /tmp/mock_servers.pid && "
        "sleep 3 && "
        "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8924/gmail/v1/users/me/messages', timeout=5)\" 2>&1 && "
        "echo MOCK_READY || echo MOCK_STARTED_ANYWAY"
    ]
    result = subprocess.run(launch_cmd, capture_output=True, text=True, timeout=15)
    print(f"[{task_id}] Mock injection: stdout={result.stdout.strip()}, stderr={result.stderr.strip()[:200]}")
