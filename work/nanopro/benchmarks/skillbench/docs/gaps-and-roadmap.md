# SkillBench: Gaps and Roadmap

**Last updated:** 2026-01-25
**Status:** Ready for private beta (core infrastructure complete)

---

## What Works Today

### Core Flow
- [x] Upload skill (SKILL.md or .zip)
- [x] Run baseline vs augmented evaluation
- [x] Generate behavioral profile (HTML)
- [x] Generate signed scorecard (JSON)
- [x] Serve at stable URLs (`/p/:slug`, `/s/:slug`)
- [x] Embeddable widget (`/embed/:slug`)

### Trust Infrastructure
- [x] Ed25519 signatures on scorecards
- [x] Published public keys (`/.well-known/keys.json`)
- [x] Verification endpoint (`/verify/:slug`)
- [x] CLI verification (`./skillbench verify <url>`)
- [x] Reproducibility fields (suite seed, config digest, adapter version, model ID)

### Anti-Gaming (Partial)
- [x] Suite integrity module (`harness/suite_integrity.py`)
- [x] Seeded variant generation code
- [x] Canary detection logic
- [x] Authoritative test output with hash
- [x] Shortcut detection wired into trace analysis
- [x] Integrity warnings included in traces.json
- [ ] **NOT YET:** Tasks don't use seeded variants (need template tasks)

### Infrastructure
- [x] SQLite database persistence (`harness/database.py`)
- [x] IP-based rate limiting (configurable)
- [x] Skill artifact hashing (SHA256)
- [x] Rate limit headers on API responses
- [x] Hosted execution mode (server-side API key)
- [x] Cost tracking (tokens + estimated USD per job)
- [x] `/api/status` and `/api/usage/:job_id` endpoints

### Agents
- [x] Mock agent (deterministic, fast)
- [x] Agentic adapter (real Claude, bounded tool loop)
- [x] Hard limits (max steps, max tool calls, wall time)
- [x] Temperature 0.0 for reproducibility

### Suites
- [x] `coding/swe-lite` — 10 bugfix tasks
- [x] `coding/tool-use` — 10 tool usage tasks

---

## Gaps: Must-Have for Real Usage

### 1. Hosted Execution ✅ DONE
**Current:** Server uses its own API key when available
**Implemented:**
- [x] API key loaded from `ANTHROPIC_API_KEY` env var
- [x] Server auto-detects hosted vs mock mode
- [x] Cost tracking per job (input/output tokens, estimated USD)
- [x] `/api/status` endpoint shows hosted mode availability
- [x] `/api/usage/:job_id` endpoint shows job cost details
- [x] Token usage aggregated from traces
- [x] Job isolation via temp directories (each eval in clean environment)
- [ ] Optional: Secrets manager integration (for production)
- [ ] Optional: Cost alerts/limits enforcement

### 2. Persistence Layer ✅ DONE
**Current:** SQLite database in `data/skillbench.db`
**Implemented:**
- [x] SQLite database with jobs table
- [x] Job CRUD operations in `harness/database.py`
- [x] Indexes for lookup by status, slug, created_at
- [x] Thread-safe connection management

### 3. Authentication / Rate Limiting ✅ DONE
**Current:** IP-based rate limiting (10 requests/hour default)
**Implemented:**
- [x] IP-based rate limiting with configurable limits
- [x] Rate limit headers (X-RateLimit-Remaining, Retry-After)
- [x] Rate limit state persisted in database
- [ ] Optional: API key system for higher limits
- [ ] Optional: Simple login for job history

### 4. Suite Variants (Wire Up Anti-Gaming)
**Current:** Code exists but tasks are static
**Needed:** Tasks use seeded variants per run
**Why:** Prevent overfitting to specific task content

**Work required:**
- [ ] Add variant templates to task definitions
- [ ] Generate variants at runtime using suite seed
- [ ] Verify canary checks catch shortcuts

### 5. Trace Persistence ✅ DONE
**Current:** Full traces saved alongside profile/scorecard
**Implemented:**
- [x] Agentic adapter writes full trace to file (`SKILLBENCH_TRACE_OUTPUT`)
- [x] run_task.py captures trace path in results
- [x] Server aggregates traces from all task results
- [x] Traces saved as `traces.json` in output directory
- [x] `/t/:slug` endpoint serves traces with cache headers
- [x] Profile page links to traces URL

---

## Gaps: Should-Have Before Charging

### 6. Skill Artifact Hashing ✅ DONE
**Current:** SHA256 of uploaded skill content stored in scorecard
**Implemented:**
- [x] `compute_skill_digest()` hashes skill files on upload
- [x] Digest stored in database and passed to scorecard generation
- [x] `skill.artifact_digest` populated in scorecard

### 7. Job Queue / Workers
**Current:** Single-threaded Flask, blocking
**Needed:** Background worker queue (Celery, RQ, or simple)
**Why:** Handle concurrent uploads, don't block on long evals

### 8. HTTPS / Production Server
**Current:** Flask dev server on HTTP
**Needed:** Gunicorn/uvicorn behind nginx, TLS cert
**Why:** Security, reliability

### 9. Error Monitoring
**Current:** Errors go to stderr
**Needed:** Sentry or similar
**Why:** Know when things break in production

### 10. More Suites
**Current:** 2 suites, 20 tasks total
**Needed:** 5-10 suites covering different domains
**Ideas:**
- [ ] `core.refactor` — Test-preserving code changes
- [ ] `core.docs` — Documentation generation quality
- [ ] `core.security` — Catch common vulnerabilities
- [ ] `core.data` — Data transformation tasks

---

## Gaps: Nice-to-Have (Growth)

### 11. Regression Tracking
Compare skill versions over time. "v1.2 improved reliability by 5% vs v1.1"

### 12. Marketplace API
Programmatic access for platforms to pull profiles, verify signatures, embed widgets.

### 13. Public Gallery
Browse verified skills. Filter by suite performance. Discovery mechanism.

### 14. Third-Party Attestation
Let other parties run suites and co-sign results. Multiple independent verifiers.

### 15. Skill Diff View
Visual comparison of what changed between skill versions.

---

## Priority Order for "Private Beta"

1. ~~**Hosted execution**~~ ✅ — Users can try without API key
2. ~~**Rate limiting**~~ ✅ — Prevent abuse
3. ~~**Database**~~ ✅ — Jobs survive restarts
4. ~~**Trace persistence**~~ ✅ — Debugging capability
5. **Wire up variants** — Partial: shortcut detection active, seeded templates TODO

**Status: Ready for Private Beta** (all blockers addressed)

---

## Architecture Notes for Future Work

### Database Schema (Proposed)
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    status TEXT,  -- queued, running, complete, failed
    stage TEXT,
    progress INTEGER,
    skill_path TEXT,
    skill_digest TEXT,
    output_slug TEXT,
    error_message TEXT,
    suite_id TEXT,
    suite_seed INTEGER,
    config_digest TEXT,
    trace_path TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_slug ON jobs(output_slug);
```

### Worker Architecture (Proposed)
```
[Web Server] → [Redis Queue] → [Worker Pool]
                                    ↓
                            [Isolated Sandbox]
                                    ↓
                            [S3/Local Storage]
```

### Secrets Management
- `ANTHROPIC_API_KEY` — For hosted execution
- `SIGNING_KEY_PATH` — Ed25519 private key
- `DATABASE_URL` — PostgreSQL connection
- `REDIS_URL` — Queue backend

---

## Non-Goals (Explicit Scope Limits)

- **Not a benchmark leaderboard** — We show behavioral profiles, not rankings
- **Not a skill marketplace** — We verify skills, marketplaces sell them
- **Not an agent framework** — We evaluate skills, not build agents
- **Not multi-tenant SaaS (yet)** — Single-instance deployment first
