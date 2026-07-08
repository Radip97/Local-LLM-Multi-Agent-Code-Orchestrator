import os
from typing import Dict, Any
from src.core.config import EXCLUDED_DIRS, LLM_DEBUGGER_MODEL, LLM_DEBUGGER_BASE_URL, LLM_API_KEY, LLM_BASE_URL
from src.core.llm import LLMClient

class RootCauseAnalyzer:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir
        
        # Instantiate LLMClient specifically using the debugger base URL and model name
        base_url = LLM_DEBUGGER_BASE_URL or LLM_BASE_URL or "http://localhost:1234/v1"
        model = LLM_DEBUGGER_MODEL or "qwen2.5-coder-1.5b-instruct-128k"
        self.llm = LLMClient(base_url=base_url, model=model, api_key=LLM_API_KEY)

    def analyze(self, parsed_error: Dict[str, Any], dependency_graph: Dict[str, Any]) -> str:
        """
        Determines the root cause using the lightweight Qwen-1.5B Debugger model.
        """
        error_type = parsed_error.get("error_type", "unknown")
        raw = parsed_error.get("raw_output", "")
        
        # 1. Collect codebase contents to provide context to the debugger
        source_code = ""
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if any(file.endswith(ext) for ext in [".js", ".py", ".html", ".css"]):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.target_dir)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        source_code += f"\n--- File: {rel_path} ---\n{content}\n"
                    except Exception:
                        pass

        # 2. Construct the debugger prompt
        system_prompt = (
            "You are an expert debugger and system analyzer. Your job is to analyze compile/test failures "
            "and identify the exact root cause of the bug in the codebase.\n"
            "CRITICAL: Do NOT write code snippets, patches, or code blocks in your response. "
            "You are strictly forbidden from writing markdown code blocks (e.g. ```javascript or ```python) or code lines. "
            "Explain the bug and the steps to fix it conceptually using ONLY plain English text."
        )
        
        prompt = (
            "We are working on a coding task. The test suite failed. Diagnose the root cause.\n\n"
            f"--- Target Codebase ---\n{source_code}\n\n"
            f"--- Error Type: {error_type} ---\n"
            f"--- Raw Test/Build Output ---\n{raw}\n\n"
            "Based on the codebase files and the test error output, identify the bug.\n"
            "Analyze and output:\n"
            "1. What is the root cause of the error?\n"
            "2. Which file, function, and lines are causing the issue?\n"
            "3. Conceptual steps to fix the issue (do NOT write code blocks or lines, explain conceptually using plain English)."
        )
        
        # 3. Call the Qwen 1.5B debugger model
        print(f"Calling debugger agent ({self.llm.model}) to analyze error...")
        try:
            analysis = self.llm.call(prompt, system_prompt)
            
            # Post-process: Programmatically strip out any code blocks the model generated anyway
            import re
            analysis = re.sub(r'```.*?```', '[Code block removed by system for security]', analysis, flags=re.DOTALL)
            
            root_cause_summary = f"Debugger Analysis ({self.llm.model}):\n{analysis}"
        except Exception as e:
            root_cause_summary = f"Root cause identified as {error_type} error. Details:\n{raw}\n(Debugger failed: {e})"
            
        return root_cause_summary
