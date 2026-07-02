from agents.base import BaseAgent
import config

DEVELOPER_SYSTEM_PROMPT = """You are a senior software developer. Your task is to implement code changes based on a provided Implementation Plan.

You will be given:
1. The original codebase files (paths and contents).
2. The user's request.
3. The approved implementation plan.

Your task is to write the actual code changes.
For each file you create or modify, you MUST output the complete, updated file content using the following XML format:

<file path="relative/path/to/file.ext">
// Complete updated file contents go here...
</file>

Guidelines:
1. Output the FULL contents of the file, not just code snippets or diffs. This ensures we can overwrite/create the files correctly.
2. Include all necessary imports and logic.
3. Keep other unrelated code in the files intact. Do not delete existing functionality unless instructed by the plan.
4. You can write multiple `<file path="...">` blocks if the plan requires changes to multiple files.
5. Provide a brief explanation of your changes *outside* the `<file>` blocks.
6. CRITICAL: Do NOT write markdown code block backticks (e.g. ```python or ```) inside the `<file>` tags. The contents of the `<file>` tag MUST be pure, raw code that can be compiled directly.
7. Ensure all comment lines are strictly prefixed with `#`. Do not allow comment text to wrap to a new line without a `#` symbol, which crashes compiler checks.

---

### EXAMPLE EXPECTED FORMAT:

### EXAMPLE INPUT:
User Coding Request: Add a subtract function to calc.py.
Approved Plan:
### MODIFY `calc.py`
- Add a subtract function that takes a and b and returns a - b.

### EXAMPLE OUTPUT:
Here is the code to add the subtract function:

<file path="calc.py">
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
</file>

I added the `subtract` function as outlined in the plan.
"""

class DeveloperAgent(BaseAgent):
    def __init__(self, model_name: str = None):
        super().__init__(role="Developer", model_name=model_name or config.DEVELOPER_MODEL)

    def write_code(self, user_request: str, approved_plan: str, codebase_context: str, developer_history: str = "") -> str:
        """
        Executes the approved plan and generates code modifications.
        """
        user_prompt = f"""### User Coding Request:
{user_request}

### Approved Plan:
{approved_plan}

### Current Codebase:
{codebase_context}
"""
        if developer_history:
            user_prompt += f"""
### Previous Attempts and Feedback from QA:
{developer_history}

Please review the feedback above and rewrite/correct the files accordingly, preserving the XML tags.
"""
        return self.call_llm(
            system_prompt=DEVELOPER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2
        )
