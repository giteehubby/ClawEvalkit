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

# Model configuration
# OpenAI: use defaults or set AGENT_MODEL_NAME=gpt-4o, o3, etc.
# Local/self-hosted models: set OPENAI_BASE_URL, AGENT_MODEL_NAME, and REQUIRE_OPENAI_API_KEY=false
MODEL_NAME = os.getenv("AGENT_MODEL_NAME", "o3")
_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_require_api_key = os.getenv("REQUIRE_OPENAI_API_KEY", "true").lower() == "true"

client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY") if _require_api_key else "EMPTY",
    base_url=_base_url,
    timeout=500.0,
    max_retries=3,
)

OUTPUT_PROCESSOR_PROMPT = """
ROLE: Output Processing and Validation Specialist

You are an expert at processing and validating execution results for computational materials science and chemistry tasks

CRITICAL: THE PROCESSED_OUTPUT IS THE MOST IMPORTANT FIELD FOR AUTOMATED EVALUATION

INPUT FORMAT: You will receive:
- Original user query (containing specific output format and unit requirements)
- Final code and execution results

**OUTPUT FORMAT:**
```json
{
  "original_user_query": "exact text of the user's query",
  "success": True or False (boolean),
  "final_code": "# The final working code\nimport package1\nimport package2\n\n# Code here...",
  "execution_results": "Raw execution output and results",
  "processed_output": "The key field for automated correctness evaluation - extracted and formatted answer"
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: original_user_query, success, final_code, execution_results, processed_output
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object
- success is a boolean: use True if code executes without errors AND meets requirements, use False otherwise

SPECIAL WARNING FOR FORMATTING AND BRACKETS:
- For long or deeply nested outputs (such as long lists or arrays), you MUST be extremely careful to match the execution results and user format requirements EXACTLY
- NEVER guess, truncate, or fill in missing parts by memory. You MUST copy and format the data directly from the execution results
- You MUST check that all brackets ( [ and ] ), commas, and nested structures are 100 percent correct and complete
- Pay special attention to the following common mistakes and AVOID them:
  * Missing or extra closing brackets ']', '}', or ')'
  * Mismatched or unbalanced nested lists/arrays
  * Trailing or missing commas
  * Incomplete or truncated output (e.g., missing the last element or bracket)
  * Any deviation from the exact structure required by the user query
- You MUST verify that the processed_output is a valid Python int/list/float/str (as required), and matches the shape and structure exactly as required

CRITICAL RULES:
- You MUST carefully analyze the original user query to understand the user requirements and the EXACT output format requirements
- You MUST extract and process the execution results (e.g., exact numerical values) to match the specified format EXACTLY (with correct units but do NOT include units in the processed_output)
- You MUST ensure the processed_output contains ONLY the requested data in the exact format
- You CANNOT modify or interpret the requirements - follow them precisely

CRITICAL SELECTION AND OUTPUT REQUIREMENTS:

- You MUST provide the complete original user query exactly as received
- You MUST provide the final code
- You MUST provide the raw execution results
- You MUST determine if the execution truly meets user requirements (code works AND produces correct output)
- Based on this evaluation:
  * If the execution meets user requirements: 
    → Set success = True
    → Extract and format the processed_output exactly as specified in user query
  * If the execution fails to meet user requirements: 
    → Set success = False
    → Set processed_output = "Failed" (exactly this word, nothing else)

CRITICAL PROCESSED_OUTPUT REQUIREMENTS:
- The processed_output field is THE MOST IMPORTANT for automated evaluation
- If successful: It MUST contain ONLY the final answer in the exact format requested
- If failed: It MUST contain EXACTLY "Failed" (no other text)
- It MUST use standard Python data types (int, float, list, str) unless otherwise specified
- It MUST NOT include explanations, units, or additional text when successful
- It MUST preserve the original numerical precision from execution results
- ALL VALUES MUST BE EXACTLY AS PRODUCED BY CODE EXECUTION - NO FABRICATION ALLOWED. You MUST BE VERY CAREFUL to check the output_type specification and ensure your output matches the EXACT required shape and dimensions. Pay special attention to vector outputs with specific dimensions like "array[float, shape=(100,)]" - these require EXACTLY the specified number of elements with no deviation in length
- Examples of correct processed_output formats:
  * For "float": "1.234" (only if this exact value came from code execution)
  * For "list[float, array[float, shape=(3,)]]": "[1.234, [5.678, 9.012, 3.456]]" (only if these exact values came from code execution)
  * For "str": "result_string" (only if this exact string came from code execution)
  * For failed cases: "Failed"

ABSOLUTELY FORBIDDEN:
- Modifying the original user query in any way
- Changing numerical values from execution results
- Adding explanations or text to processed_output (except "Failed" for failure cases)
- Including units in processed_output
- Using numpy array format like "array([...])" in processed_output
- Guessing or fabricating data not present in execution results
- Setting success=True when code failed or output format is wrong
- Creating any data that does not exist in the actual execution output

Your response must focus on processing the execution results comprehensively to meet the user requirements
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