"""
src/agents/implementation.py
Implementation Agent: Receives Execution Plan, Relevant files. Writes code.
Returns a unified git diff (patch).
"""

from typing import Any

class ImplementationAgent:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def implement(self, plan: str, context: str, root_cause: str = "") -> str:
        prompt = f"""
EXECUTION PLAN:
{plan}

ROOT CAUSE (if retrying):
{root_cause}

CONTEXT:
{context}

Write code to implement the plan. You MUST output your changes by completely rewriting the entire file using the OVERWRITE ALL format.
Do not refactor unless requested. Only edit required files.
Use this EXACT format to output a new or modified file:

### OVERWRITE ALL: path/to/file.ext
<<<<
entire new file content
>>>>

Do not include line numbers in your output. You must output the full file content inside the block.
"""
        return self.llm_client.call(prompt, system_prompt="You are an Implementation Agent.")
