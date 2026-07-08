"""
src/runner/compiler.py
Compiler Runner: Automatically execute build commands.
Capture stdout, stderr, exit code, build time.
"""

import subprocess
import time
from typing import Dict, Any

class CompilerRunner:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir

    def run(self, command: str) -> Dict[str, Any]:
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=self.target_dir, 
                capture_output=True, 
                text=True
            )
            duration = time.time() - start_time
            
            return {
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "duration_sec": duration,
                "success": result.returncode == 0
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "command": command,
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "duration_sec": duration,
                "success": False
            }
