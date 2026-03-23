# Adaptive Agents for vLLM Models

This guide explains how to use adaptive agents with vLLM models like Qwen3-Coder-30B-A3B-Instruct-FP8.

## Required SDK Modification

**Note**: This modification is compatible with both vLLM and OpenAI models. You don't need to revert these changes when switching back to OpenAI models.

### 1. Locate and Modify the SDK File

File: `.venv/lib/python3.12/site-packages/agents/_run_impl.py`

Find the `execute_tools_and_side_effects` method, locate the elif branch around line 348 (openai-agents==0.2.8), and replace the whole elif branch with:

```python
    elif (
        not output_schema or output_schema.is_plain_text()
    ) and not processed_response.has_tools_or_approvals_to_run():
        # Check if agent has a target_output_type to inject
        if hasattr(agent, 'target_output_type') and agent.output_type is None:
            # Agent started with output_type=None and now has target to set
            agent.output_type = agent.target_output_type
            
            if agent.target_output_type is not None:
                # Has structured output target, run again to get output_schema
                return SingleStepResult(
                    original_input=original_input,
                    model_response=new_response,
                    pre_step_items=pre_step_items,
                    new_step_items=new_step_items,
                    next_step=NextStepRunAgain(),
                )
        
        # Normal path or target_output_type is None
        return await cls.execute_final_output(
            agent=agent,
            original_input=original_input,
            new_response=new_response,
            pre_step_items=pre_step_items,
            new_step_items=new_step_items,
            final_output=potential_final_output_text or "",
            hooks=hooks,
            context_wrapper=context_wrapper,
        )
```

## 2. Start vLLM Server

For example: 
```bash
source .venv/bin/activate
nohup env CUDA_VISIBLE_DEVICES=0,1,2,3 VLLM_USE_DEEP_GEMM=1 vllm serve open_source_models/Qwen3-Coder-30B-A3B-Instruct-FP8 \
    --max-model-len 262144 \
    --enable-expert-parallel \
    --data-parallel-size 4 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --served-model-name Qwen3-Coder-30B-A3B-Instruct-FP8 \
    --port 8000 \
    --host 127.0.0.1 > vllm_qwen3_coder_30b.log 2>&1 &
```

## 3. Set Environment Variables

Set these environment variables to use adaptive agents with vLLM:

```bash
export USE_ADAPTIVE_AGENTS=true
export OPENAI_BASE_URL=http://localhost:8000/v1
export AGENT_MODEL_NAME=Qwen3-Coder-30B-A3B-Instruct-FP8
export REQUIRE_OPENAI_API_KEY=false
```

Or add them to your `.env` file in the project root:

```bash
USE_ADAPTIVE_AGENTS=true
OPENAI_BASE_URL=http://localhost:8000/v1
AGENT_MODEL_NAME=Qwen3-Coder-30B-A3B-Instruct-FP8
REQUIRE_OPENAI_API_KEY=false
```

## 4. Usage

After setting the environment variables above, all CASCADE components will automatically use adaptive agents with vLLM.

For running benchmarks or tests, see [DEVELOPMENT.md](../deep_solver_benchmark/DEVELOPMENT.md).