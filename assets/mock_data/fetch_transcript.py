#!/usr/bin/env python3
"""
Mock YouTube Transcript Fetcher.

Reads transcript data from scenario file at:
  /app/mounts/youtube-transcript/scenario.json

Usage:
  python3 scripts/fetch_transcript.py <video_url_or_id>
  python3 scripts/fetch_transcript.py https://www.youtube.com/watch?v=HNMedge2401
"""
import json
import os
import sys
from pathlib import Path

SCENARIO_FILE = os.environ.get(
    "YOUTUBE_TRANSCRIPT_SCENARIO_FILE",
    "/app/mounts/youtube-transcript/scenario.json"
)


def get_transcript(video_arg: str) -> dict:
    """Get transcript for a video from scenario data."""
    if not Path(SCENARIO_FILE).exists():
        return {
            "status": "error",
            "message": f"Scenario file not found: {SCENARIO_FILE}",
            "video_id": video_arg,
        }

    with open(SCENARIO_FILE) as f:
        data = json.load(f)

    videos = data.get("videos", {})
    video_arg_lower = video_arg.lower()

    # Extract video ID from URL if needed
    video_id = video_arg
    if "watch?v=" in video_arg:
        import re
        match = re.search(r'[?&]v=([^&]+)', video_arg)
        if match:
            video_id = match.group(1)

    # Search by video ID or URL
    for vid_key, vid_data in videos.items():
        vid_url = vid_data.get("url", "")
        if vid_key == video_id or vid_key == video_arg:
            return vid_data
        if video_id in vid_url or video_arg in vid_url:
            return vid_data

    return {
        "status": "error",
        "message": f"No transcript found for: {video_arg}",
        "video_id": video_id,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fetch_transcript.py <video_url_or_id>")
        sys.exit(1)

    video_arg = sys.argv[1]
    result = get_transcript(video_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
