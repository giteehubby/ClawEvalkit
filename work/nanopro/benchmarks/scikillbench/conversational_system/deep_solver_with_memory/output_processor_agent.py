from __future__ import annotations

import os
import logging
from agents import Agent, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from openai import AsyncOpenAI  
import asyncio
from typing import Any, Callable, TypeVar, Optional

# Import output types
from .output_types import FinalResult

T = TypeVar('T')

# Model configuration (configurable via environment variables)
# OpenAI: use defaults or set AGENT_MODEL_NAME=gpt-4o, o3, etc.
# Local/self-hosted models: set OPENAI_BASE_URL, AGENT_MODEL_NAME, and REQUIRE_OPENAI_API_KEY=false
MODEL_NAME = os.getenv("AGENT_MODEL_NAME", "o3")
_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_require_api_key = os.getenv("REQUIRE_OPENAI_API_KEY", "true").lower() == "true"

client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY") if _require_api_key else "EMPTY",  # vLLM doesn't need real API key
    base_url=_base_url,
    timeout=500.0,
    max_retries=3,
)

OUTPUT_PROCESSOR_PROMPT = """
ROLE: Output Processing and Validation Specialist

You are an expert at processing and validating execution results for computational materials science and chemistry tasks

CRITICAL: THE PROCESSED_OUTPUT IS THE MOST IMPORTANT FIELD FOR USER UNDERSTANDING AND EVALUATION

INPUT FORMAT: You will receive:
- Original user query
- Either THREE debug results from parallel debugging attempts (each containing final code and execution output)
- Or SUCCESSFUL EXECUTION with Final Code and Execution Results (if no debugging was needed)

**OUTPUT FORMAT:**
```json
{
  "original_user_query": "exact text of the user's query",
  "success": True or False (boolean),
  "final_code": "# The final working code\nimport package1\nimport package2\n\n# Code here...",
  "execution_results": "Raw execution output and results",
  "processed_output": "The key field for evaluation - carefully explained answer and analysis to the user's query"
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: original_user_query, success, final_code, execution_results, processed_output
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object
- success is a boolean: use True if code executes without errors AND meets requirements, use False otherwise

CRITICAL RULES:
- You MUST carefully analyze the original user query to understand the user requirements and what they need
- You MUST select the best debug result based on the selection criteria in STEP 1 and STEP 2
- You MUST ensure the processed_output contains the requested data and analysis to address the user's query

CRITICAL SELECTION AND OUTPUT REQUIREMENTS:

FOR SUCCESSFUL EXECUTION (if received):
- You MUST provide the complete original user query exactly as received
- You MUST provide the final working code
- You MUST provide the raw execution results
- You MUST determine if the execution truly meets user requirements (code works AND produces correct output)
- Based on this evaluation:
  * If the execution meets user requirements: 
    → Set success = True
    → Write the processed_output to address the user's query
  * If the execution fails to meet user requirements: 
    → Set success = False
    → Set processed_output = "Failed" (exactly this word, nothing else)

FOR DEBUGGING RESULTS (if received):
STEP 1: EVALUATE ALL THREE DEBUG RESULTS (MANDATORY)
- ANALYZE each debug result to determine:
  * Does the code execute without errors?
  * Does the execution output contain the required data?
- RANK the three results from best to worst based on:
  * Successful execution (no errors)
  * Presence of required data in output
  * Quality and completeness of results

STEP 2: SELECT THE BEST RESULT (MANDATORY)
- CHOOSE the debug result that best meets the user requirements
- If multiple results are successful, pick the one with most complete/accurate data
- If all results have errors or missing data, pick the one closest to success
- IMPORTANT: If multiple debug results produce the same or very similar output, this identical result is more likely to be correct and should be preferred most of the time

STEP 3: PROCESS THE SELECTED BEST RESULT (MANDATORY) 
Based on the best result selected in STEP 2:
- You MUST provide the complete original user query exactly as received
- You MUST provide the final working code from the SELECTED BEST result
- You MUST provide the raw execution results from the SELECTED BEST result
- You MUST determine if the SELECTED BEST result truly successful (code works AND produces correct output)
- Based on this evaluation of the SELECTED BEST result:
  * If the SELECTED BEST result meets user requirements: 
    → Set success = True
    → Write the processed_output to address the user's query
  * If the SELECTED BEST result still fails to meet user requirements: 
    → Set success = False 
    → Set processed_output = "Failed" (exactly this word, nothing else)
- MOST IMPORTANT: Based on the solution provided by the SELECTED BEST result, you MUST write the processed_output to properly address the original user query OR "Failed" if the SELECTED BEST result is insufficient

Your response must focus on selecting the best result and processing it comprehensively to meet the user requirements. Start immediately with CRITICAL SELECTION AND OUTPUT REQUIREMENTS
"""

class OutputProcessorAgent(Agent):
    """Output Processor Agent for selecting best debug result and final processing."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

async def create_output_processor_agent() -> OutputProcessorAgent:
    """Create an output processor agent focused on selecting best debug result and processing."""
    try:
        # # Check API key availability (commented out for non-OpenAI models)
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        agent = OutputProcessorAgent(
                name="OutputProcessorAgent",
                instructions=OUTPUT_PROCESSOR_PROMPT,
                model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
                output_type=FinalResult,
                # Only set this model_settings for OpenAI GPT-5's reasoning models (gpt-5, gpt-5-mini, or gpt-5-nano), for other models, do not set this model_settings
                # model_settings=ModelSettings(reasoning=Reasoning(effort="medium"), verbosity="low")
                )
      
        return agent
        
    except Exception as e:
        print(f"Error creating output processor agent: {e}")
        raise

# Export the necessary functions and classes
__all__ = [
    "OutputProcessorAgent",
    "create_output_processor_agent"
] 