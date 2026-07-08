"""
src/runner/tester.py
Test Runner: Run tests, lint, formatter, type checker, coverage.
"""

from src.runner.compiler import CompilerRunner

class TestRunner(CompilerRunner):
    def run_tests(self, test_command: str) -> str:
        """Runs the test command and summarizes failures."""
        result = self.run(test_command)
        
        if result["success"]:
            return "Tests Passed"
        
        # Summarize
        summary = f"Tests Failed (Exit code {result['exit_code']})\n"
        if result["stderr"]:
            summary += result["stderr"][-2000:] # Last 2k chars
        else:
            summary += result["stdout"][-2000:]
            
        return summary
