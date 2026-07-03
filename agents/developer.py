from agents.base import BaseAgent
import config

DEVELOPER_SYSTEM_PROMPT = """You are a senior software developer. Your task is to implement code changes based on a provided Implementation Plan.

You will be given:
1. The original codebase files (paths and contents).
2. The user's request.
3. The approved implementation plan.

Your task is to write the actual code changes.
For each file you create or modify, you MUST output the code inside the XML tags: `<file path="...">...</file>`.

Guidelines for Outputting Code:
1. For existing files you want to MODIFY, you can either:
   a) Use one or more SEARCH/REPLACE blocks inside the `<file path="...">` tag (highly recommended for large files). Use this format:
<<<<<<< SEARCH
[exact lines from original file that you want to replace]
=======
[new replacement lines]
>>>>>>> REPLACE
   b) Or write the COMPLETE file content inside the `<file path="...">` tag (highly recommended for small files to avoid search/replace matching errors).

2. For NEW files you want to CREATE, write the complete new file contents inside the `<file path="...">` tag. Do NOT use search/replace markers.
3. Keep other unrelated code in the files intact. Do not delete existing functionality unless instructed by the plan.
4. You can write multiple `<file path="...">` blocks if the plan requires changes to multiple files.
5. Provide a brief explanation of your changes *outside* the `<file>` blocks.
6. CRITICAL: Do NOT write markdown code block backticks (e.g. ```python or ```) inside the `<file>` tags. The contents of the `<file>` tag MUST be pure code or search/replace blocks.

---

### EXAMPLE EXPECTED FORMAT FOR MODIFICATIONS:

### EXAMPLE INPUT:
User Coding Request: Add a subtract function to calc.py.
Approved Plan:
### MODIFY `calc.py`
- Add a subtract function that takes a and b and returns a - b.

### EXAMPLE OUTPUT:
Here is the code to add the subtract function using a SEARCH/REPLACE block:

<file path="calc.py">
<<<<<<< SEARCH
def add(a, b):
    return a + b
=======
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
>>>>>>> REPLACE
</file>

I added the `subtract` function as outlined in the plan.
"""

class DeveloperAgent(BaseAgent):
    def __init__(self, model_name: str = None):
        super().__init__(role="Developer", model_name=model_name or config.DEVELOPER_MODEL)

    def write_code(self, user_request: str, approved_plan: str, codebase_context: str,
                   developer_history: str = "", image_paths: list = None) -> str:
        """
        Executes the approved plan and generates code modifications.
        If image_paths are provided, they are sent as visual reference to the LLM.
        """
        import re
        image_paths = image_paths or []
        # Truncate approved_plan if it is too long to save context
        plan_summary = approved_plan
        if len(approved_plan) > 1500:
            # Try to extract the Proposed Changes section
            match = re.search(r"(## Proposed Changes[\s\S]*)", approved_plan)
            if match:
                plan_summary = match.group(1)
            else:
                plan_summary = approved_plan[:1500] + "\n... (plan truncated for context) ..."

        image_note = ""
        if image_paths:
            image_note = f"\n\n### Visual Reference Images:\nYou have been provided {len(image_paths)} reference image(s). Match the aesthetic, color palette, and visual style shown in these images in your implementation.\n"

        user_prompt = f"""### User Coding Request:
{user_request}{image_note}

### Approved Plan Specification:
{plan_summary}

### Current Codebase:
{codebase_context}
"""
        if developer_history:
            user_prompt += f"""
### Previous Attempts and Feedback from QA:
{developer_history}

Please review the feedback above and rewrite/correct the files accordingly, preserving the XML tags.
"""
        return self.call_llm_with_images(
            system_prompt=DEVELOPER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            image_paths=image_paths
        )
