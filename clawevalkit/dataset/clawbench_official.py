"""ClawBench Official — 250 个任务，NanoBotAgent 执行 + Pytest 验证。

评分方式: pytest 规则评分 (0~100)。
需要 claw-bench-official 仓库中的 claw_bench 包。

支持两种执行模式:
  - use_docker=True:  在 Docker 容器内运行 NanoBotAgent
  - use_docker=False: 通过 subprocess 调用 claw_bench (原有模式，默认)
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .base import BaseBenchmark
from ..utils.log import log


# Docker 配置
DOCKER_IMAGE = os.environ.get("CLAWBENCH_DOCKER_IMAGE", "clawbase-nanobot:v1")
TMP_WORKSPACE = "/tmp/clawbench_workspace"


class ClawBenchOfficial(BaseBenchmark):
    DISPLAY_NAME = "ClawBench Official"
    TASK_COUNT = 250
    SCORE_RANGE = "0-100"

    def __init__(self, base_dir: Path = None, output_dir: Path = None, use_docker: bool = False):
        super().__init__(base_dir=base_dir, output_dir=output_dir)
        self._use_docker_default = use_docker

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """评测入口：根据 use_docker 选择执行模式。"""
        use_docker = kwargs.pop("use_docker", self._use_docker_default)
        parallel = kwargs.pop("parallel", 1)
        kwargs.pop("force", None)
        kwargs.pop("max_turns", None)

        if use_docker:
            return self._evaluate_docker(
                model_key=model_key,
                config=config,
                sample=sample,
                parallel=parallel,
                **kwargs
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
                **kwargs
            )

    def _evaluate_native(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """Native mode: 通过 subprocess 调用 claw_bench 包进行评测。"""
        bench_dir = self.base_dir / "benchmarks" / "claw-bench"
        if not bench_dir.exists():
            return {"score": 0, "passed": 0, "total": 0, "error": f"bench dir not found: {bench_dir}"}

        sample_n = sample or 250
        result_dir = self.results_dir / "clawbench-official"
        result_dir.mkdir(parents=True, exist_ok=True)

        # 内联 Python 脚本调用 claw_bench
        script = f"""
import json, random, sys
from pathlib import Path
from claw_bench.adapters.openclaw import OpenClawAdapter
from claw_bench.core.task_loader import load_all_tasks
from claw_bench.core.runner import run_single_task

tasks, dirs = load_all_tasks(Path('tasks'))
sample_n = min({sample_n}, len(tasks))
indices = random.sample(range(len(tasks)), sample_n) if sample_n < len(tasks) else list(range(len(tasks)))

adapter = OpenClawAdapter()
adapter.setup({{'model': '{config["model"]}', 'timeout': 300}})

results = []
for i, idx in enumerate(indices):
    task = tasks[idx]
    td = dirs[task.id]
    try:
        r = run_single_task(task, td, adapter, timeout=300)
        print(f'  [{{i+1}}/{{sample_n}}] {{task.id}}: {{"PASS" if r.passed else "FAIL"}} score={{r.score:.2f}}', flush=True)
        results.append({{'id': task.id, 'passed': r.passed, 'score': r.score}})
    except Exception as e:
        print(f'  [{{i+1}}/{{sample_n}}] {{task.id}}: ERROR {{e}}', flush=True)
        results.append({{'id': task.id, 'passed': False, 'score': 0.0}})

avg = sum(r['score'] for r in results) / max(len(results), 1) * 100
passed = sum(1 for r in results if r['passed'])
print(json.dumps({{'score': round(avg, 1), 'passed': passed, 'total': len(results), 'results': results}}))
"""
        env = os.environ.copy()
        env["OPENAI_COMPAT_BASE_URL"] = config["api_url"]
        env["OPENAI_COMPAT_API_KEY"] = config["api_key"]

        try:
            proc = subprocess.run(
                ["python3", "-c", script],
                cwd=str(bench_dir), capture_output=True, text=True, timeout=7200, env=env,
            )
            # 提取最后一行 JSON
            for line in reversed(proc.stdout.strip().splitlines()):
                try:
                    data = json.loads(line)
                    self.save_result("clawbench-official", model_key, data, f"{model_key}_sample{sample_n}.json")
                    return data
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            return {"score": 0, "passed": 0, "total": 0, "error": str(e)[:300]}

        return {"score": 0, "passed": 0, "total": 0, "error": "no output"}

    def _evaluate_docker(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        parallel: int = 1,
        **kwargs
    ) -> dict:
        """Docker mode: 在容器内运行 NanoBotAgent 执行任务。"""
        bench_dir = self.base_dir / "benchmarks" / "claw-bench"
        if not bench_dir.exists():
            return {"score": 0, "passed": 0, "total": 0, "error": f"bench dir not found: {bench_dir}"}

        # 加载任务列表
        tasks, task_dirs = self._load_tasks(bench_dir)
        if not tasks:
            return {"score": 0, "total": 0, "error": "no tasks found"}

        # 按 task_ids 过滤（同时匹配 id 和 dir_name）
        task_ids = kwargs.get("task_ids") or kwargs.get("task_id_list")
        if task_ids:
            task_id_set = set(task_ids)
            tasks = [t for t in tasks if t["id"] in task_id_set or t.get("dir_name") in task_id_set]
            if not tasks:
                log(f"No tasks matched task_ids: {task_ids}")
                return {"score": 0, "passed": 0, "total": 0, "error": f"no tasks matched: {task_ids}"}

        # 按 category 过滤
        category = kwargs.get("category")
        if category:
            tasks = [t for t in tasks if category in t.get("domain", "")]
            if not tasks:
                log(f"No tasks matched category: {category}")
                return {"score": 0, "passed": 0, "total": 0, "error": f"no tasks matched category: {category}"}

        # 采样
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "clawbench-official" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        openclawpro_dir = kwargs.get("openclawpro_dir") or Path(
            os.getenv("OPENCLAWPRO_DIR", str(self.base_dir / "OpenClawPro"))
        )

        def run_single_task_docker(task: dict) -> dict:
            """在 Docker 容器内执行单个任务。"""
            tid = task["id"]
            result_file = out_dir / f"{tid}.json"

            # 检查缓存
            if result_file.exists():
                try:
                    cached = json.loads(result_file.read_text())
                    if cached.get("status") == "success":
                        log(f"[{tid}] Found cached result, skipping")
                        return cached
                except Exception:
                    pass

            # 生成容器名
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            short_model = re.sub(r"[^a-zA-Z0-9.\-_]", "_", config["model"].rsplit("/", 1)[-1])
            container_name = f"clawbench_{tid}_{short_model}_{timestamp}"

            result = {
                "task_id": tid,
                "model_key": model_key,
                "status": "error",
                "passed": False,
                "score": 0.0,
                "error": None
            }

            workspace_path = None

            try:
                # 准备工作空间
                workspace_path = tempfile.mkdtemp(prefix=f"clawbench_docker_{tid}_")
                host_workspace = Path(workspace_path) / "workspace"
                host_workspace.mkdir(parents=True, exist_ok=True)

                # 复制任务数据到工作空间
                self._prepare_task_workspace(task_dirs[tid], host_workspace)

                # 构建环境变量
                proxy_http = os.environ.get('HTTP_PROXY', '')
                proxy_https = os.environ.get('HTTPS_PROXY', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTP_PROXY={proxy_http}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                ]

                # 根据 provider 传递正确的 API key
                provider = config.get("provider", "openrouter")
                if provider == "minimax":
                    minimax_api_key = os.getenv("MINIMAX_API_KEY", "")
                    env_args.extend(["-e", f"MINIMAX_API_KEY={minimax_api_key}"])
                else:
                    env_args.extend(["-e", f"OPENROUTER_API_KEY={openrouter_api_key}"])

                # 启动容器
                self._start_container(
                    container_name, workspace_path, bench_dir, openclawpro_dir, env_args
                )
                log(f"[{container_name}] Container started")

                # 构建并执行 agent 脚本
                timeout = task.get("timeout", 300)
                exec_script = self._build_exec_script(task, config, timeout)
                exec_proc, elapsed_time = self._run_agent_in_container(container_name, exec_script, timeout)
                log(f"[{container_name}] Agent finished in {elapsed_time:.2f}s, returncode={exec_proc.returncode}")

                # 复制结果
                try:
                    result_json = self._copy_result_from_container(container_name, workspace_path)
                    if result_json.exists():
                        agent_result = json.loads(result_json.read_text())
                        result["status"] = agent_result.get("status", "error")
                        result["passed"] = agent_result.get("passed", False)
                        result["score"] = agent_result.get("score", 0.0)
                        result["error"] = agent_result.get("error", "")
                        result["details"] = agent_result.get("details", "")
                        result["checks_total"] = agent_result.get("checks_total", 0)
                        result["checks_passed"] = agent_result.get("checks_passed", 0)
                        result["workspace_files"] = agent_result.get("workspace_files", [])
                        result["execution_time"] = agent_result.get("execution_time", 0)
                        # 保存 transcript
                        transcript = agent_result.get("transcript", [])
                        if transcript:
                            self._save_transcript(model_key, tid, transcript)
                        log(f"[{container_name}] Agent result: passed={result['passed']}, score={result['score']:.4f}")
                    else:
                        result["error"] = "agent_result.json not found"
                        log(f"[{container_name}] agent_result.json not found")
                except Exception as e:
                    result["error"] = f"Failed to load agent result: {e}"
                    log(f"[{container_name}] Failed to load agent result: {e}")

            except subprocess.TimeoutExpired:
                result["error"] = f"Timeout after {task.get('timeout', 300)} seconds"
            except Exception as exc:
                log(f"[{container_name}] Execution error: {exc}")
                result["error"] = str(exc)
            finally:
                # 清理
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                if workspace_path:
                    shutil.rmtree(workspace_path, ignore_errors=True)

            # 保存结果
            try:
                result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                log(f"[{tid}] Failed to save result: {e}")

            return result

        # 执行任务
        results = []
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker(task))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {pool.submit(run_single_task_docker, task): task["id"] for task in tasks}
                for future in as_completed(futures):
                    tid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        log(f"[{tid}] Thread exception: {exc}")
                        results.append({"task_id": tid, "status": "error", "error": str(exc)})

        # 汇总结果
        scores = [r["score"] for r in results if r.get("status") == "success"]
        passed = sum(1 for r in results if r.get("passed"))
        overall = round(sum(scores) / len(scores) * 100, 1) if scores else 0
        final = {
            "score": overall,
            "passed": passed,
            "total": len(tasks),
            "details": results
        }
        self.save_result("clawbench-official", model_key, final, "result.json")
        return final

    def _load_tasks(self, bench_dir: Path) -> tuple[list, dict]:
        """加载 claw-bench-official 任务列表。"""
        # 这里需要在容器内执行，所以我们返回任务目录的元数据
        tasks_root = bench_dir / "tasks"
        if not tasks_root.exists():
            return [], {}

        tasks = []
        task_dirs = {}

        for domain_dir in sorted(tasks_root.iterdir()):
            if not domain_dir.is_dir() or domain_dir.name.startswith("_"):
                continue
            for task_dir in sorted(domain_dir.iterdir()):
                if not task_dir.is_dir():
                    continue
                toml_path = task_dir / "task.toml"
                if not toml_path.exists():
                    continue
                # 读取基本信息
                try:
                    import tomli
                    with open(toml_path, "rb") as f:
                        raw = tomli.load(f)
                    if "task" in raw:
                        raw = {**raw.pop("task"), **raw}
                    task_id = raw.get("id", task_dir.name)
                    timeout = raw.get("timeout", 300)
                    dir_name = task_dir.name  # 如 comm-002-contact-list
                    tasks.append({
                        "id": task_id,
                        "dir_name": dir_name,
                        "timeout": timeout,
                        "domain": raw.get("domain", "")
                    })
                    task_dirs[task_id] = task_dir
                    # 同时用目录名作为别名，方便按目录名查找
                    task_dirs[dir_name] = task_dir
                except Exception as e:
                    log(f"Failed to load task {task_dir.name}: {e}")
                    continue

        return tasks, task_dirs

    def _prepare_task_workspace(self, task_dir: Path, workspace: Path) -> None:
        """复制任务数据到工作空间。"""
        # 复制 environment/data 目录
        data_dir = task_dir / "environment" / "data"
        if data_dir.exists():
            for f in data_dir.iterdir():
                dest = workspace / f.name
                if f.is_file():
                    shutil.copy2(f, dest)
                elif f.is_dir():
                    shutil.copytree(f, dest, dirs_exist_ok=True)

        # 读取 instruction.md
        instruction_path = task_dir / "instruction.md"
        if instruction_path.exists():
            workspace.joinpath("instruction.md").write_text(instruction_path.read_text())

    def _save_transcript(self, model_key: str, task_id: str, transcript: list):
        """保存 agent 轨迹到文件。

        保存到: outputs/clawbench-official/transcripts/{model}/{task}/transcript.json
        """
        try:
            trans_path = self.results_dir / "clawbench-official" / "transcripts" / model_key / task_id
            trans_path.mkdir(parents=True, exist_ok=True)
            (trans_path / "transcript.json").write_text(
                json.dumps(transcript, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log("[%s] Saved transcript to %s", task_id, trans_path / "transcript.json")
        except Exception:
            pass  # transcript 保存失败不影响主流程

    def _start_container(
        self,
        container_name: str,
        workspace_path: str,
        bench_dir: Path,
        openclawpro_dir: Path,
        env_args: list
    ) -> None:
        """启动 Docker 容器并挂载相关目录。"""
        workspace_inner = os.path.join(workspace_path, "workspace")

        volume_mounts = [
            "-v", f"{bench_dir}:/app/claw-bench:rw",
            "-v", f"{workspace_inner}:{TMP_WORKSPACE}:rw",
        ]

        # 挂载 OpenClawPro
        if openclawpro_dir and openclawpro_dir.exists():
            volume_mounts.extend(["-v", f"{openclawpro_dir}:/root/OpenClawPro:rw"])

        docker_run_cmd = [
            "docker", "run", "-d",
            "--network", "host",
            "--name", container_name,
            *volume_mounts,
            *env_args,
            DOCKER_IMAGE,
            "/bin/bash", "-c", "tail -f /dev/null",
        ]
        r = subprocess.run(docker_run_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Container startup failed:\n{r.stderr}")

        # 启动后立即安装缺失依赖（显式 unset 容器内 ENV 代理）
        install_env = {k: v for k, v in os.environ.items()
                       if k.lower() not in ('http_proxy', 'https_proxy')}
        subprocess.run(
            ["docker", "exec",
             "-e", "http_proxy=",
             "-e", "https_proxy=",
             container_name,
             "pip", "install", "-q", "tomli", "pytest-json-report"],
            capture_output=True, text=True, env=install_env, timeout=120
        )

    def _build_exec_script(self, task: dict, config: dict, timeout: int) -> str:
        """构建在容器内执行的 NanoBotAgent 脚本。"""
        # 根据 provider 选择 API key 环境变量
        provider = config.get("provider", "openrouter")
        if provider == "minimax":
            api_key_env = "MINIMAX_API_KEY"
        else:
            api_key_env = "OPENROUTER_API_KEY"

        task_id = task["id"]

        return f"""
import sys
import subprocess
import os

# 确保依赖已安装（通常由 _start_container 预装）
try:
    import tomli
except ImportError:
    pass
try:
    import pytest_json_report
except ImportError:
    pass

import json
import time
import shutil
from pathlib import Path

sys.path.insert(0, '/root/OpenClawPro')
sys.path.insert(0, '/app/claw-bench/src')

from harness.agent.nanobot import NanoBotAgent
from claw_bench.core.task_loader import load_task
from claw_bench.core.verifier import verify_task

# 容器内路径
workspace = Path('{TMP_WORKSPACE}')
task_dir = Path('/app/claw-bench/tasks')

# 根据 task_id 找到任务目录
# task_id 格式可能是 comm-008，目录结构是 tasks/communication/comm-008
task_subdir = None

# 首先尝试直接匹配
for domain_dir in task_dir.iterdir():
    if domain_dir.is_dir() and not domain_dir.name.startswith('_'):
        candidate = domain_dir / '{task_id}'
        if candidate.exists() and (candidate / 'task.toml').exists():
            task_subdir = candidate
            break

# 如果没找到，尝试遍历所有 task.toml 查找匹配的 id
if not task_subdir:
    for domain_dir in task_dir.iterdir():
        if domain_dir.is_dir() and not domain_dir.name.startswith('_'):
            for task_candidate in domain_dir.iterdir():
                if task_candidate.is_dir():
                    toml_file = task_candidate / 'task.toml'
                    if toml_file.exists():
                        try:
                            import tomli
                            with open(toml_file, 'rb') as f:
                                raw = tomli.load(f)
                            if 'task' in raw:
                                raw = {{**raw.pop('task'), **raw}}
                            if raw.get('id') == '{task_id}':
                                task_subdir = task_candidate
                                break
                        except:
                            pass
            if task_subdir:
                break

if not task_subdir:
    output = {{'status': 'error', 'passed': False, 'score': 0.0, 'error': 'task dir not found for {task_id}'}}
    (workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False))
    print('DONE')
    sys.exit(0)

# 加载任务配置
task = load_task(task_subdir)

# 准备工作空间（复制数据）
data_dir = task_subdir / 'environment' / 'data'
if data_dir.exists():
    for f in data_dir.iterdir():
        dest = workspace / f.name
        if f.is_file():
            shutil.copy2(f, dest)
        elif f.is_dir():
            shutil.copytree(f, dest, dirs_exist_ok=True)

# 运行环境设置脚本
setup_sh = task_subdir / 'environment' / 'setup.sh'
if setup_sh.exists():
    import subprocess
    subprocess.run(['bash', str(setup_sh), str(workspace.resolve())],
                   cwd=str(task_subdir), capture_output=True, timeout=30)

# 读取指令
instruction_path = task_subdir / 'instruction.md'
instruction = instruction_path.read_text() if instruction_path.exists() else task.description

# 重写相对路径
abs_workspace = str(workspace.resolve())
instruction = instruction.replace('workspace/', f'{{abs_workspace}}/')
instruction = instruction.replace('`workspace/', f'`{{abs_workspace}}/')

# 添加工作空间前缀
full_prompt = (
    f"IMPORTANT: You must write all output files to the absolute path: {{abs_workspace}}/\\n"
    f"Do NOT use relative paths. Use the exact absolute path above.\\n"
    f"Execute shell commands to create the required files.\\n\\n"
    f"{{instruction}}"
)

# 获取 API key
api_key = os.environ.get('{api_key_env}', '')

# 创建 NanoBotAgent
agent = NanoBotAgent(
    model='{config["model"]}',
    api_url='{config["api_url"]}',
    api_key=api_key,
    workspace=workspace,
    timeout={timeout},
    disable_safety_guard=True,
)

system_prompt = \"\"\"You are an expert agent working in a restricted environment.
Solve the task efficiently. Run all processes in the foreground without user input.
Provide a complete, functional solution.\"\"\"

try:
    start_time = time.time()
    result = agent.execute(
        full_prompt,
        session_id='clawbench_{task_id}',
        workspace=workspace,
        system_prompt=system_prompt,
        max_iterations=100,
    )
    elapsed = time.time() - start_time

    # 验证结果
    verify_result = verify_task(task_subdir, workspace)
    passed = verify_result.passed
    score = verify_result.weighted_score if verify_result.weighted_score is not None else (
        verify_result.checks_passed / max(verify_result.checks_total, 1)
    )

    # 列出工作空间文件用于调试
    workspace_files = [str(f.relative_to(workspace)) for f in workspace.iterdir() if f.is_file()]

    # 提取 transcript
    transcript = result.transcript if hasattr(result, 'transcript') and result.transcript else []
    # 尝试从 .sessions 目录读取（NanoBotAgent 会自动保存）
    if not transcript:
        session_file = workspace / '.sessions' / f'clawbench_{task_id}.jsonl'
        if session_file.exists():
            try:
                import json as _json
                transcript = [_json.loads(line) for line in session_file.read_text().strip().splitlines() if line.strip()]
            except Exception:
                pass

    # 安全序列化 transcript
    safe_transcript = []
    for entry in transcript:
        try:
            json.dumps(entry)
            safe_transcript.append(entry)
        except (TypeError, ValueError):
            safe_transcript.append({{str(k): str(v) for k, v in entry.items()}} if isinstance(entry, dict) else str(entry))

    output = {{
        'status': result.status if hasattr(result, 'status') else 'success',
        'passed': passed,
        'score': score,
        'details': verify_result.details,
        'checks_total': verify_result.checks_total,
        'checks_passed': verify_result.checks_passed,
        'workspace_files': workspace_files,
        'execution_time': elapsed,
        'error': result.error if hasattr(result, 'error') else '',
        'transcript': safe_transcript,
    }}
except Exception as e:
    import traceback
    output = {{
        'status': 'error',
        'passed': False,
        'score': 0.0,
        'execution_time': 0,
        'error': str(e),
        'traceback': traceback.format_exc(),
    }}

(workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
print('DONE')
"""

    def _run_agent_in_container(self, container_name: str, exec_script: str, timeout: int) -> tuple:
        """在容器内执行 agent 脚本，返回 (process_result, elapsed_time)。"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(exec_script)
            script_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", script_path, f"{container_name}:/tmp/exec_nanobot.py"],
                check=True, capture_output=True
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

        start_time = time.perf_counter()
        exec_proc = subprocess.run(
            ["docker", "exec", container_name, "python3", "/tmp/exec_nanobot.py"],
            capture_output=True, text=True, timeout=timeout + 60
        )
        elapsed = time.perf_counter() - start_time
        # 输出容器内日志用于调试
        if exec_proc.stdout:
            for line in exec_proc.stdout.strip().splitlines()[-20:]:
                log(f"  [container] {line}")
        if exec_proc.stderr:
            for line in exec_proc.stderr.strip().splitlines()[-10:]:
                log(f"  [container-err] {line}")
        return exec_proc, elapsed

    def _copy_result_from_container(self, container_name: str, workspace_path: str) -> Path:
        """从容器复制结果到 host。"""
        result_file_host = Path(workspace_path) / "agent_result.json"
        subprocess.run(
            ["docker", "cp", f"{container_name}:{TMP_WORKSPACE}/agent_result.json", str(result_file_host)],
            capture_output=True
        )
        return result_file_host


    def _compute_summary(self, model_key: str, all_task_ids: list, results: list) -> dict:
        """Compute summary for clawbench_official."""
        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success" and r.get("scores")]
        avg = round(sum(scores) / len(scores), 3) if scores else 0
        passed = len(scores)
        score = avg
        total = len(all_task_ids)
        scored = len(results)
        return {
            "model": model_key,
            "score": score,
            "passed": passed,
            "failed": scored - passed,
            "pending": total - scored,
            "total": total,
            "details": results
        }

    def _load_summary(self, bench_key: str, model_key: str) -> dict:
        """Load saved summary file."""
        result_f = self.results_dir / bench_key / f"{model_key}.json"
        if result_f.exists():
            try:
                data = json.loads(result_f.read_text())
                return {"score": data["score"], "passed": data.get("passed", 0), "total": data["total"]}
            except Exception:
                pass
        return {"score": 0, "passed": 0, "total": 0}

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("clawbench-official")
        if not result_dir:
            return None
        for f in sorted(result_dir.glob(f"{model_key}*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                return {"score": data["avg_score"] if "avg_score" in data else data.get("score", 0),
                        "passed": data.get("passed", 0), "total": data.get("total", 0)}
            except Exception:
                pass
        return None
