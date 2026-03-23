#!/usr/bin/env python3
"""
Database layer for SkillBench.

SQLite for now (zero dependencies), easy to migrate to PostgreSQL later.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Iterator
import threading

# Thread-local storage for connections
_local = threading.local()

# Default database path
DEFAULT_DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "skillbench.db"


def get_db_path() -> pathlib.Path:
    """Get database path, creating directory if needed."""
    import os
    # Use RAILWAY_VOLUME_MOUNT_PATH for persistent storage if available
    railway_volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_volume:
        path = pathlib.Path(railway_volume) / "skillbench.db"
    else:
        path = pathlib.Path(os.environ.get("SKILLBENCH_DB_PATH", str(DEFAULT_DB_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Get a database connection (thread-safe)."""
    if not hasattr(_local, "connection") or _local.connection is None:
        db_path = get_db_path()
        _local.connection = sqlite3.connect(str(db_path), check_same_thread=False)
        _local.connection.row_factory = sqlite3.Row
        _init_schema(_local.connection)

    yield _local.connection


def _init_schema(conn: sqlite3.Connection) -> None:
    """Initialize database schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            stage TEXT DEFAULT 'loading',
            progress INTEGER DEFAULT 0,
            skill_path TEXT,
            skill_digest TEXT,
            output_slug TEXT,
            error_message TEXT,
            suite_id TEXT DEFAULT 'core-bugfix',
            suite_version TEXT DEFAULT '1.0.0',
            suite_seed INTEGER,
            runner_version TEXT DEFAULT '0.2.0',
            config_digest TEXT,
            trace_path TEXT,
            metadata TEXT,
            -- Cost tracking for hosted execution
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0.0,
            execution_mode TEXT DEFAULT 'hosted'
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_slug ON jobs(output_slug);
        CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

        CREATE TABLE IF NOT EXISTS rate_limits (
            ip_address TEXT PRIMARY KEY,
            request_count INTEGER DEFAULT 0,
            window_start TEXT NOT NULL,
            last_request TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON rate_limits(window_start);
    """)
    conn.commit()


# =============================================================================
# Job Operations
# =============================================================================

@dataclass
class Job:
    id: str
    created_at: str
    updated_at: str
    status: str = "queued"
    stage: str = "loading"
    progress: int = 0
    skill_path: Optional[str] = None
    skill_digest: Optional[str] = None
    output_slug: Optional[str] = None
    error_message: Optional[str] = None
    suite_id: str = "core-bugfix"
    suite_version: str = "1.0.0"
    suite_seed: Optional[int] = None
    runner_version: str = "0.2.0"
    config_digest: Optional[str] = None
    trace_path: Optional[str] = None
    metadata: Optional[dict] = None
    # Cost tracking for hosted execution
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    execution_mode: str = "hosted"

    def to_dict(self) -> dict:
        d = asdict(self)
        # Don't serialize None values
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Job":
        d = dict(row)
        if d.get("metadata"):
            d["metadata"] = json.loads(d["metadata"])
        return cls(**d)


def create_job(
    job_id: str,
    skill_path: str,
    skill_digest: Optional[str] = None,
    suite_id: str = "core-bugfix",
    suite_version: str = "1.0.0",
    suite_seed: Optional[int] = None,
) -> Job:
    """Create a new job."""
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO jobs (id, created_at, updated_at, skill_path, skill_digest,
                            suite_id, suite_version, suite_seed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (job_id, now, now, skill_path, skill_digest, suite_id, suite_version, suite_seed))
        conn.commit()

    return get_job(job_id)


def get_job(job_id: str) -> Optional[Job]:
    """Get a job by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row:
            return Job.from_row(row)
    return None


def update_job(job_id: str, **kwargs) -> Optional[Job]:
    """Update job fields."""
    if not kwargs:
        return get_job(job_id)

    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Handle metadata specially
    if "metadata" in kwargs and kwargs["metadata"] is not None:
        kwargs["metadata"] = json.dumps(kwargs["metadata"])

    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [job_id]

    with get_connection() as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        conn.commit()

    return get_job(job_id)


def list_jobs(status: Optional[str] = None, limit: int = 100) -> list[Job]:
    """List jobs, optionally filtered by status."""
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [Job.from_row(row) for row in rows]


def delete_old_jobs(days: int = 30) -> int:
    """Delete jobs older than N days. Returns count deleted."""
    cutoff = datetime.now(timezone.utc).isoformat()[:10]  # Just date part
    # This is a simple approximation; in production use proper date math

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM jobs WHERE created_at < date(?, ?)",
            (cutoff, f"-{days} days")
        )
        conn.commit()
        return cursor.rowcount


# =============================================================================
# Rate Limiting
# =============================================================================

@dataclass
class RateLimitStatus:
    allowed: bool
    remaining: int
    reset_at: str
    retry_after_seconds: Optional[int] = None


def check_rate_limit(
    ip_address: str,
    max_requests: int = 10,
    window_seconds: int = 3600,
) -> RateLimitStatus:
    """
    Check if IP is within rate limits.

    Returns RateLimitStatus with allowed=True if request should proceed.
    """
    now = datetime.now(timezone.utc)
    window_start = now.isoformat()

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM rate_limits WHERE ip_address = ?",
            (ip_address,)
        ).fetchone()

        if row:
            # Check if window has expired
            stored_window = datetime.fromisoformat(row["window_start"].replace("Z", "+00:00"))
            elapsed = (now - stored_window).total_seconds()

            if elapsed >= window_seconds:
                # Reset window
                conn.execute("""
                    UPDATE rate_limits
                    SET request_count = 1, window_start = ?, last_request = ?
                    WHERE ip_address = ?
                """, (window_start, window_start, ip_address))
                conn.commit()
                return RateLimitStatus(
                    allowed=True,
                    remaining=max_requests - 1,
                    reset_at=(now.replace(second=0, microsecond=0)).isoformat(),
                )
            else:
                # Check count
                count = row["request_count"]
                if count >= max_requests:
                    reset_at = stored_window.replace(second=0, microsecond=0)
                    retry_after = int(window_seconds - elapsed)
                    return RateLimitStatus(
                        allowed=False,
                        remaining=0,
                        reset_at=reset_at.isoformat(),
                        retry_after_seconds=retry_after,
                    )
                else:
                    # Increment
                    conn.execute("""
                        UPDATE rate_limits
                        SET request_count = request_count + 1, last_request = ?
                        WHERE ip_address = ?
                    """, (now.isoformat(), ip_address))
                    conn.commit()
                    return RateLimitStatus(
                        allowed=True,
                        remaining=max_requests - count - 1,
                        reset_at=stored_window.isoformat(),
                    )
        else:
            # First request from this IP
            conn.execute("""
                INSERT INTO rate_limits (ip_address, request_count, window_start, last_request)
                VALUES (?, 1, ?, ?)
            """, (ip_address, window_start, window_start))
            conn.commit()
            return RateLimitStatus(
                allowed=True,
                remaining=max_requests - 1,
                reset_at=now.isoformat(),
            )


def cleanup_rate_limits(older_than_hours: int = 24) -> int:
    """Clean up old rate limit entries."""
    cutoff = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM rate_limits WHERE last_request < datetime(?, ?)",
            (cutoff, f"-{older_than_hours} hours")
        )
        conn.commit()
        return cursor.rowcount


# =============================================================================
# Migration Helper
# =============================================================================

def migrate_from_json(json_path: pathlib.Path) -> int:
    """Migrate jobs from old JSON file to database."""
    if not json_path.exists():
        return 0

    data = json.loads(json_path.read_text())
    count = 0

    for job_id, job_data in data.items():
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO jobs
                    (id, created_at, updated_at, status, stage, progress,
                     skill_path, output_slug, error_message, runner_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id,
                    job_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    job_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    job_data.get("status", "complete"),
                    job_data.get("stage", "complete"),
                    job_data.get("progress", 100),
                    job_data.get("skill_path"),
                    job_data.get("output_slug"),
                    job_data.get("error_message"),
                    job_data.get("runner_version", "0.2.0"),
                ))
                conn.commit()
                count += 1
        except Exception as e:
            print(f"Failed to migrate job {job_id}: {e}")

    return count


if __name__ == "__main__":
    # Test database operations
    import uuid

    print("Testing database operations...")

    # Create a job
    job_id = str(uuid.uuid4())[:8]
    job = create_job(job_id, "/tmp/test-skill", skill_digest="abc123")
    print(f"Created job: {job.id}")

    # Update it
    job = update_job(job_id, status="running", progress=50)
    print(f"Updated job: status={job.status}, progress={job.progress}")

    # Test rate limiting
    status = check_rate_limit("127.0.0.1", max_requests=5)
    print(f"Rate limit: allowed={status.allowed}, remaining={status.remaining}")

    # List jobs
    jobs = list_jobs(limit=5)
    print(f"Total jobs: {len(jobs)}")

    print("Done!")
