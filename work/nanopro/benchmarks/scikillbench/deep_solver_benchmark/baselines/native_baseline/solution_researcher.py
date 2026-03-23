from pydantic import BaseModel, Field
from typing import Optional, List, Any, Callable, TypeVar, Dict
import json
import re
import os
import sys
import asyncio
import subprocess
import time

from agents import Agent, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Import output types
from .output_types import SolutionResponse

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

# Prompt for the solution researcher agent
SOLUTION_RESEARCHER_PROMPT = """
ROLE: Materials Science Solution Researcher

You are a materials science and chemistry researcher who specializes in generating code solutions

NOTE: All the requests here require code implementation. Your primary goal is to provide working code solutions with accurate package dependencies based on your knowledge

**OUTPUT FORMAT:**
```json
{
  "original_user_query": "exact text of the user's query",
  "required_packages": ["package1", "package2", "package3"],
  "code_solution": "# Complete Python code\nimport package1\nimport package2\n\n# Your solution code here..."
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: original_user_query, required_packages, code_solution
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object

CRITICAL REQUIREMENTS FOR YOUR RESPONSE:
    - You MUST provide the complete original user query exactly as received
    - You MUST identify and list ALL required packages needed for the solution
    - You MUST provide complete, executable, correct and relevant Python code based on verified sources
    - Your code MUST include environment variable setup where needed (e.g., os.getenv("MP_API_KEY") for Materials Project queries. Note: this is not provided in the user query but are stored in the environment variables exactly called 'MP_API_KEY')
    - When using MPRester, you MUST use the code 'from mp_api.client import MPRester' with os.getenv('MP_API_KEY') instead of 'from pymatgen.ext.matproj import MPRester'
    - No hallucinations are allowed

Your ultimate goal is to provide a complete code solution that addresses the user's needs
"""


async def create_solution_researcher_agent() -> Agent:
    """Create and return a solution researcher agent with structured output."""
    try:
        # # Check API key availability (commented out for non-OpenAI models)
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        agent = Agent(
            name="SolutionResearcherAgent",
            instructions=SOLUTION_RESEARCHER_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            output_type=SolutionResponse,
            # Only set this model_settings for OpenAI GPT-5's reasoning models (gpt-5, gpt-5-mini, or gpt-5-nano), for other models, do not set this model_settings
            # model_settings=ModelSettings(reasoning=Reasoning(effort="medium"), verbosity="low")
        )
        
        return agent
        
    except Exception as e:
        print(f"Error creating solution researcher agent: {e}")
        raise

# Export the necessary functions and classes
__all__ = [
    "create_solution_researcher_agent"
]