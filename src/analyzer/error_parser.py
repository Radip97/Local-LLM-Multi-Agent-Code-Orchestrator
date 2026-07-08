"""
src/analyzer/error_parser.py
Error Parser: Parse compiler output. Collapse duplicate errors. 
Identify syntax, type, missing imports, etc.
"""

import re
from typing import Dict, Any, List

class ErrorParser:
    def parse(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """
        Parse output and return structured JSON.
        """
        combined = stdout + "\n" + stderr
        
        # Simple deduplication by line
        lines = combined.split('\n')
        unique_lines = []
        seen = set()
        for line in lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_lines.append(line)

        # Basic identification heuristics
        error_type = "unknown"
        if re.search(r'syntaxerror|invalid syntax', combined, re.IGNORECASE):
            error_type = "syntax"
        elif re.search(r'typeerror|cannot assign', combined, re.IGNORECASE):
            error_type = "type"
        elif re.search(r'importerror|modulenotfound|no such module', combined, re.IGNORECASE):
            error_type = "missing_import"
        elif re.search(r'nameerror|undefined', combined, re.IGNORECASE):
            error_type = "missing_symbol"

        return {
            "error_type": error_type,
            "raw_output": "\n".join(unique_lines[-50:]), # Keep tail
            "is_fatal": "fatal" in combined.lower() or "panic" in combined.lower()
        }
