# Aim: Recipe Harness 轨迹实验

## 终极目标
glm-5-modelhub 完成 4 bench × 6 harness 组合实验，产出完整轨迹 trace，用于论文数据。

## 当前阶段
**ClawEval 最后收尾**：仅剩 collab_cmd(160/199) 和 collaboration(149/199) 两个进程在跑。control/procedure/memory/combo 均已完成。

## 最新状态（2026-05-11 01:36 更新）
| 实验 | 进度 | 均分 | 状态 |
|------|------|------|------|
| collab_cmd×agentbench | 39/39 ✅ | 47.3% | DONE |
| combo×agentbench | 39/39 ✅ | 91.0% | DONE |
| collab_cmd×pinchbench | 23/23 ✅ | 57.4% | DONE |
| combo×pinchbench | 23/23 ✅ | 89.5% | DONE |
| combo×claweval | 199/199 ✅ | 18.3% | DONE |
| memory×claweval | 199/199 ✅ | 25.2% | DONE |
| procedure×claweval | 199/199 ✅ | 55.6% | DONE |
| control×claweval | 199/199 ✅ | 60.5% | DONE |
| collab_cmd×claweval | 160/199 🔄 | ~40.4% | RUNNING (PID 72191) |
| collaboration×claweval | 149/199 🔄 | ~61.6% | RUNNING (PID 43962) |
| collab_cmd×clawbench-official | ~250/250 ❌ | 全超时 | DONE but all zero |
| combo×clawbench-official | ~250/250 ❌ | 全超时 | DONE but all zero |

## 检查清单（每次触发后执行）
1. 检查进程数：`ps aux | grep "run.py.*glm-5-modelhub" | grep -v grep | wc -l`
2. 检查 claweval 4 个 harness 进度（目标 199/199）
3. **若 procedure 进程死了（日志停 >10min），立刻重启**：
   ```bash
   nohup python3.11 run.py --model glm-5-modelhub --judge-model glm-5 --bench claweval --harness procedure --docker --parallel 1 >> work/exp1_hello_clawevalkit/assets/logs/harness_claweval_procedure_$(date +%Y%m%d_%H%M%S).log 2>&1 &
   ```
4. collab_cmd/collaboration/control 同理，检查日志活跃度后重启
5. **若全部 claweval 完成 → 更新 HTML 报告**：重新运行数据收集脚本后调用 show
6. clawbench-official 全超时（API 太慢），暂时搁置，不要等待

## 关键路径
- 日志：`work/exp1_hello_clawevalkit/assets/logs/harness_claweval_*.log`
- 输出：`outputs/harness/{harness}/claweval/glm-5-modelhub/*/result.json`
- HTML：`work/exp1_hello_clawevalkit/assets/output/exp1_harness_report.html`
- 运行命令：`/opt/homebrew/bin/python3.11 run.py --model glm-5-modelhub --judge-model glm-5 --bench claweval --harness {h} --docker --parallel 1`

## 注意事项
- procedure harness 有 web_fetch 无限循环 bug，进程容易挂死 → 需要定时重启
- 每次检查后必须再挂下一个提醒（sleep 1800）
