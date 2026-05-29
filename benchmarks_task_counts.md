# Benchmarks Task Counts

**统计时间**: 2026-05-01  |  **Multimodal 过滤**: 开启（默认）

| Benchmark | 总任务数 | 被过滤任务 | 实际参与数 | 备注 |
|-----------|---------|-----------|-----------|------|
| zclawbench | 116 | 0 | **116** | 无 multimodal 过滤 |
| claweval | 300 | 101 | **199** | 默认排除 tags: [multimodal] 任务 |
| pinchbench | 23 | 0 | **23** | 无 multimodal 过滤 |
| agentbench | 39 | 0 | **39** | 无 multimodal 过滤 |
| skillsbench | 88 | 20 | **68** | SKIP_TASKS=20，EASY_SKIP_TASKS=11 |
| tribe | 8 | 0 | **8** | 代码硬编码 TASK_COUNT=8 |
| wildclawbench | 60 | 0 | **60** | 代码硬编码 TASK_COUNT=60 |
| clawbench-official | 303 | 0 | **303** | 动态扫描 task.toml |
| skillbench | 22 | 0 | **22** | 代码硬编码 TASK_COUNT=22 |

**注**: `--exclude_multimodal` 是 run.py 的默认行为，仅 `claweval` 基准有 `tags: [multimodal]` 任务。