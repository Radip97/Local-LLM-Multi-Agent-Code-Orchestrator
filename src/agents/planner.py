"""
src/agents/planner.py
Planning Agent: Receives Task, Relevant files, Dependency graph. Produces Execution Plan. No code.
"""

from typing import Dict, Any

class PlanningAgent:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def plan(self, task: str, context: str, dependency_graph: Dict[str, Any]) -> str:
        prompt = f"""
TASK:
{task}

CONTEXT:
{context}

Produce an Execution Plan. Do not write any code. Only list the steps required to modify the target files.
"""
        return self.llm_client.call(prompt, system_prompt="You are a Planning Agent.")
