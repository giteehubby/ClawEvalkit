# Runner Architecture (Draft)

## Decision: Docker-based Sandbox (v0)
- Mirrors SWE-bench practice of per-task Docker containers to ensure reproducibility and simple dependency pinning.
- Compatible with GitHub Actions/local runs; contributors can build/run images without special tooling.
- Provides configurable resource limits (CPU, memory) and the ability to disable network access by default.
- Later phases can explore Firecracker/MicroVM runners for stronger isolation or hosted services.

## Components
1. **Base Image (`skillbench/base`)**
   - OS: Ubuntu 22.04
   - Pre-installed: Python 3.11, git, build-essential, jq, Node 18 (for CLI tasks), Claude Code tooling requirements.
   - Non-root user `agent`.
2. **Task Pack Layer**
   - For each task pack, optional `Dockerfile` extending `skillbench/base` to install extra deps (e.g., specific Python libs, LaTeX for PDF tasks).
   - Pack manifest specifies the image tag.
3. **Runner CLI Workflow**
   - Build/pull the appropriate image.
   - Mount workspace containing benchmark harness, task assets, and skill files.
   - Inject environment variables (model API keys, run metadata) via `.env` file.
   - Execute `python /harness/run_task.py --task <id> --mode baseline|augmented`.
4. **Result Capture**
   - Runner writes JSON + logs to `/output/<task-id>/<mode>/`.
   - Host CLI collects outputs, aggregates, and generates final report.

## Security Defaults
- Network: disabled by default using Docker `--network none`; packs can opt-in to limited network (e.g., for specific APIs) via manifest flag.
- File access: mount is read-only except for `/output` and a temporary `/workspace`.
- Skills run as non-root user; no sudo access.
- Optional policy checks (scan skill directory for suspicious scripts) before mounting.

## Configuration Schema (draft excerpt)
```yaml
runner:
  type: docker
  base_image: skillbench/base:0.1.0
  task_image: skillbench/coding-swe-lite:0.1.0
  network: false
  cpu_limit: "4"
  memory_limit: "8g"
  timeout_seconds: 900
```

## Open Items
- Decide how to bundle large repos/tasks (git submodules vs downloading inside container).
- Determine caching strategy so repeated runs don’t rebuild images every time.
- Evaluate need for GPU support (probably out of scope initially).
- Provide alternative “local runner” for contributors who can’t use Docker (lower priority).
