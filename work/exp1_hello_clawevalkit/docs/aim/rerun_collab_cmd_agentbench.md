# 待重跑：collab_cmd×agentbench (glm-5-modelhub)

## 原因
在家/VPN 状态下运行，所有39个任务均 401 失败（ModelHub 内网不通，0.24s 即报错），
得分（平均47.3）是假值，已从 final_linjh 删除。

## 重跑命令（回公司内网后执行）
```bash
cd /Users/bytedance/Documents/github/ClawEvalkit
TS=$(date +%Y%m%d_%H%M%S)
nohup /opt/homebrew/bin/python3.11 run.py \
  --model glm-5-modelhub --judge-model glm-5 \
  --bench agentbench --harness collab_cmd \
  --docker --parallel 2 --force \
  >> work/exp1_hello_clawevalkit/assets/logs/rerun_collab_cmd_agentbench_${TS}.log 2>&1 &
echo "PID=$!"
```

## 完成后
```bash
# 提交结果
git add outputs/harness/collab_cmd/agentbench/glm-5-modelhub/
git commit -m "results: rerun collab_cmd×agentbench (39/39, fixed 401 errors)"
git push origin final_linjh
```
