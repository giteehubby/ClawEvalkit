"""
ZClawBench Mock Data Extractor.

从 reference trajectories 中提取 mock service 所需的 scenario 数据，
用于在容器中启动 mock servers。

支持的 mock services:
  - gmail:     Gmail API mock (port 8924)
  - calendar:  Google Calendar API mock (port 8926)
  - search:    Google Search mock (scenario file)
  - youtube:   YouTube transcript mock (scenario file)
"""
import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

# 路径配置
MOCK_DATA_DIR = Path(__file__).parent.parent.parent / "assets" / "zclawbench_mock"
GMAIL_SCENARIOS_FILE = MOCK_DATA_DIR / "gmail_scenarios.json"
CALENDAR_SCENARIOS_FILE = MOCK_DATA_DIR / "calendar_scenarios.json"
SEARCH_SCENARIOS_FILE = MOCK_DATA_DIR / "search_scenarios.json"


def _extract_gmail_scenarios_from_jsonl(jsonl_path: Path) -> Dict[str, Any]:
    """从 zclawbench.jsonl 提取所有 Gmail scenario 数据"""
    scenarios = {}

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue

            tid = row.get("task_id", "")
            traj_str = row.get("trajectory", "")
            if not traj_str:
                continue

            try:
                traj = json.loads(traj_str) if isinstance(traj_str, str) else traj_str
            except Exception:
                continue

            # 找 Gmail scenario.json 内容
            # 格式: {"name": "cb_xxx", "accounts": [...], "initial_state": {"messages": [...]}}
            gmail_scenario = None

            for msg in traj:
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_result":
                        result_raw = c.get("content", "")
                        # content can be str or list
                        if isinstance(result_raw, list):
                            result = json.dumps(result_raw)
                        elif isinstance(result_raw, str):
                            result = result_raw
                        else:
                            result = str(result_raw)
                        if (
                            result.strip().startswith("{")
                            and '"name":' in result
                            and '"accounts":' in result
                        ):
                            try:
                                parsed = json.loads(result)
                                if isinstance(parsed, dict) and "accounts" in parsed:
                                    gmail_scenario = parsed
                                    break
                            except Exception:
                                pass
                if gmail_scenario:
                    break

            if gmail_scenario:
                # scenario name -> data
                name = gmail_scenario.get("name", tid.replace("zcb_", "cb_"))
                scenarios[name] = gmail_scenario
                scenarios[tid] = gmail_scenario  # 也按 task_id 索引

    return scenarios


def _extract_calendar_scenarios_from_jsonl(jsonl_path: Path) -> Dict[str, Any]:
    """从 zclawbench.jsonl 提取所有 Calendar scenario 数据"""
    scenarios = {}

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue

            tid = row.get("task_id", "")
            traj_str = row.get("trajectory", "")
            if not traj_str:
                continue

            try:
                traj = json.loads(traj_str) if isinstance(traj_str, str) else traj_str
            except Exception:
                continue

            calendar_scenario = None

            for msg in traj:
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_result":
                        result_raw = c.get("content", "")
                        if isinstance(result_raw, list):
                            result = json.dumps(result_raw)
                        elif isinstance(result_raw, str):
                            result = result_raw
                        else:
                            result = str(result_raw)
                        if (
                            result.strip().startswith("{")
                            and '"name":' in result
                            and '"calendars":' in result
                        ):
                            try:
                                parsed = json.loads(result)
                                if isinstance(parsed, dict) and "calendars" in parsed:
                                    calendar_scenario = parsed
                                    break
                            except Exception:
                                pass
                if calendar_scenario:
                    break

            if calendar_scenario:
                name = calendar_scenario.get("name", tid.replace("zcb_", "cb_"))
                scenarios[name] = calendar_scenario
                scenarios[tid] = calendar_scenario

    return scenarios


def _extract_search_scenarios_from_jsonl(jsonl_path: Path) -> Dict[str, Any]:
    """从 zclawbench.jsonl 提取所有 Search scenario 数据"""
    scenarios = {}

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue

            tid = row.get("task_id", "")
            traj_str = row.get("trajectory", "")
            if not traj_str:
                continue

            try:
                traj = json.loads(traj_str) if isinstance(traj_str, str) else traj_str
            except Exception:
                continue

            search_scenario = None

            for msg in traj:
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_result":
                        result_raw = c.get("content", "")
                        if isinstance(result_raw, list):
                            result = json.dumps(result_raw)
                        elif isinstance(result_raw, str):
                            result = result_raw
                        else:
                            result = str(result_raw)
                        if (
                            result.strip().startswith("{")
                            and '"responses":' in result
                        ):
                            try:
                                parsed = json.loads(result)
                                if isinstance(parsed, dict) and "responses" in parsed:
                                    search_scenario = parsed
                                    break
                            except Exception:
                                pass
                if search_scenario:
                    break

            if search_scenario:
                name = search_scenario.get("name", tid.replace("zcb_", "cb_"))
                scenarios[name] = search_scenario
                scenarios[tid] = search_scenario

    return scenarios


def extract_and_save_all_scenarios(jsonl_path: Optional[Path] = None) -> None:
    """提取并保存所有 scenario 数据到资产目录"""
    if jsonl_path is None:
        jsonl_path = (
            Path(__file__).parent.parent.parent
            / "benchmarks"
            / "zclawbench"
            / "zclawbench.jsonl"
        )

    MOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    gmail = _extract_gmail_scenarios_from_jsonl(jsonl_path)
    cal = _extract_calendar_scenarios_from_jsonl(jsonl_path)
    search = _extract_search_scenarios_from_jsonl(jsonl_path)

    with open(GMAIL_SCENARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(gmail, f, ensure_ascii=False, indent=2)
    print(f"Gmail scenarios: {len(gmail)} saved to {GMAIL_SCENARIOS_FILE}")

    with open(CALENDAR_SCENARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)
    print(f"Calendar scenarios: {len(cal)} saved to {CALENDAR_SCENARIOS_FILE}")

    with open(SEARCH_SCENARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(search, f, ensure_ascii=False, indent=2)
    print(f"Search scenarios: {len(search)} saved to {SEARCH_SCENARIOS_FILE}")


def load_scenarios() -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """加载已提取的 scenario 数据"""
    gmail = {}
    cal = {}
    search = {}

    if GMAIL_SCENARIOS_FILE.exists():
        with open(GMAIL_SCENARIOS_FILE, encoding="utf-8") as f:
            gmail = json.load(f)

    if CALENDAR_SCENARIOS_FILE.exists():
        with open(CALENDAR_SCENARIOS_FILE, encoding="utf-8") as f:
            cal = json.load(f)

    if SEARCH_SCENARIOS_FILE.exists():
        with open(SEARCH_SCENARIOS_FILE, encoding="utf-8") as f:
            search = json.load(f)

    return gmail, cal, search


def get_task_scenario_name(task_id: str) -> str:
    """从 task_id 推导 scenario name"""
    return task_id.replace("zcb_", "cb_")


if __name__ == "__main__":
    extract_and_save_all_scenarios()
