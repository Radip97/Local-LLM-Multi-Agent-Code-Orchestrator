from agents.base import BaseAgent
import config

PLANNER_SYSTEM_PROMPT = """You are an expert software architect and technical planner.
Your role is to draft a comprehensive, step-by-step implementation plan to address the user's coding request.

You will be given:
1. The current codebase files (paths and contents).
2. The user's request.

Your task is to analyze the request and the existing code, then output a detailed implementation plan.
Do NOT output code implementations directly. Instead, specify exactly:
1. What files need to be modified, created, or deleted.
2. The exact logic, classes, methods, or functions that must be updated or added in each file.
3. Any potential edge cases or testing strategies.

Format your plan clearly using Markdown:
# Implementation Plan: [Feature/Bugfix Title]

## Goal
[Briefly describe what this plan accomplishes]

## Proposed Changes
List every file that needs to change. Under each file, describe the exact logic additions or modifications.
Format as:
### [MODIFY/NEW/DELETE] `relative/path/to/file`
- Detail the exact structural or behavioral changes needed here.
- (Optional) Provide pseudo-code or outline of signatures.

## Edge Cases & Testing
- Note what needs verification.
"""

class PlannerAgent(BaseAgent):
    def __init__(self, model_name: str = None):
        super().__init__(role="Planner", model_name=model_name or config.PLANNER_MODEL)

    def plan(self, user_request: str, codebase_context: str) -> str:
        """
        Generates an implementation plan.
        """
        user_prompt = f"""### User Coding Request:
{user_request}

### Current Codebase:
{codebase_context}

Please generate the step-by-step implementation plan.
"""
        return self.call_llm(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2
        )
