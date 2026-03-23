from pydantic import BaseModel, Field
from typing import List
import re


def _sanitize_output(output: str) -> str:
    """Sanitize execution output by removing problematic characters that cause JSON parsing errors."""
    if not output:
        return output
    
    # Remove null characters (\u0000) that cause JSON truncation
    sanitized = output.replace('\u0000', '')
    
    # Remove other potentially problematic control characters
    # Keep common whitespace characters but remove others
    sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
    
    return sanitized


class SolutionResponse(BaseModel):
    """Output type for Solution Researcher Agent"""
    user_id: str = Field(description="User identifier for memory search")
    original_user_query: str = Field(description="The complete original user query including requirements and expected output")
    required_packages: List[str] = Field(description="List of packages needed for the solution")
    code_solution: str = Field(description="Complete Python code solution")


class ExecutionReport(BaseModel):
    """Output type for Code Agent"""
    user_id: str = Field(description="User identifier for memory search")
    original_user_query: str = Field(description="The complete original user query")
    executed_code: str = Field(description="The actual code that was executed")
    execution_output: str = Field(description="Raw execution output, errors, logs, or results")
    needs_debugging: bool = Field(description="Whether the code needs debugging due to errors or incorrect results")
    
    def __init__(self, **data):
        # Sanitize execution_output before creating the object
        if 'execution_output' in data:
            data['execution_output'] = _sanitize_output(data['execution_output'])
        super().__init__(**data)


class DebugResult(BaseModel):
    """Output type for Debug Agents"""
    original_user_query: str = Field(description="The complete original user query")
    final_code: str = Field(description="The debugged and fixed code")
    execution_output: str = Field(description="Raw execution output, errors, logs, or results")
    
    def __init__(self, **data):
        # Sanitize execution_output before creating the object
        if 'execution_output' in data:
            data['execution_output'] = _sanitize_output(data['execution_output'])
        super().__init__(**data)


class FinalResult(BaseModel):
    """Output type for Output Processor Agent"""
    original_user_query: str = Field(description="The complete original user query")
    success: bool = Field(description="True only if code executes without errors AND meets user requirements")
    final_code: str = Field(description="The final working code")
    execution_results: str = Field(description="Raw execution output and results")
    processed_output: str = Field(description="The key field for evaluation - carefully explained answer and analysis to the user's query")
    
    def __init__(self, **data):
        # Sanitize execution_results before creating the object
        if 'execution_results' in data:
            data['execution_results'] = _sanitize_output(data['execution_results'])
        super().__init__(**data)
    