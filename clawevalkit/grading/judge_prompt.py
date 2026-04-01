# flake8: noqa
"""ZClawBench Judge 评分 prompt 模板。"""

JUDGE_PROMPT = """You are an expert evaluator for AI agent trajectories on the ZClawBench benchmark.

## Task Description
Task ID: {task_id}
Category: {category}
Task: {task_prompt}

## Agent Trajectory (conversation with tools)
{trajectory_text}

## Evaluation Dimensions

Score each dimension from 0.0 to 1.0:

1. **Task Completion** (权重 35%): Did the agent successfully complete the user's request? Were all requested components delivered (e.g., correct files, all requested sources covered)?
2. **Tool Usage** (权重 25%): Were tools used appropriately and correctly? Did the agent select the right tools for the job? Were tool calls well-formed?
3. **Reasoning & Planning** (权重 20%): Did the agent reason well step-by-step? Did it adapt when initial approaches failed?
4. **Final Answer Quality** (权重 20%): Is the final answer accurate, complete, and well-formatted?

## Output Format
Return a JSON object with the following fields:
{{
  "task_completion": 0.0-1.0,
  "tool_usage": 0.0-1.0,
  "reasoning": 0.0-1.0,
  "answer_quality": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "justification": "Brief explanation of the scores (1-3 sentences)"
}}

## Important
- Scores should reflect how well the agent performed relative to the task requirements
- If a tool failed but the agent recovered and completed the task, score reasoning higher
- If the agent ignored part of the request, task_completion should be penalized
- For final answer quality, check accuracy of information and completeness of output
"""

JUDGE_PROMPT_OFFLINE = """You are an expert evaluator for AI agent trajectories on the ZClawBench benchmark.

## Task Description
Task ID: {task_id}
Category: {category}
Task: {task_prompt}

## Reference Trajectory (from {model_name})
{trajectory_text}

## Evaluation Dimensions

Score each dimension from 0.0 to 1.0:

1. **Task Completion** (权重 35%): Did the agent successfully complete the user's request?
2. **Tool Usage** (权重 25%): Were tools used appropriately and correctly?
3. **Reasoning & Planning** (权重 20%): Did the agent reason well step-by-step?
4. **Final Answer Quality** (权重 20%): Is the final answer accurate and complete?

## Output Format
Return a JSON object with the following fields:
{{
  "task_completion": 0.0-1.0,
  "tool_usage": 0.0-1.0,
  "reasoning": 0.0-1.0,
  "answer_quality": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "justification": "Brief explanation"
}}
"""
