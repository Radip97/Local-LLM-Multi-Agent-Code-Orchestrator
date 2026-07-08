"""
src/patcher/generator.py
Patch Generator: Only receives Root cause, Relevant files. Generates smallest possible patch.
"""

from typing import Any

class PatchGenerator:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def generate_patch(self, root_cause: str, context: str) -> str:
        prompt = f"""
ROOT CAUSE:
{root_cause}

CONTEXT:
{context}

Generate the smallest possible patch to fix the error. Return your changes using SEARCH/REPLACE blocks.
Use this EXACT format:

### FILE: path/to/file.ext
<<<<
old code
====
new code
>>>>
"""
        return self.llm_client.call(prompt, system_prompt="You are a Patch Generator.")
