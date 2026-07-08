"""
src/main.py
Main entrypoint for the Local LLM Multi-Agent Code Orchestrator.
"""

import sys
import os

# Ensure the parent directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.controller import IterationController

from src.core.llm import LLMClient

def main():
    if len(sys.argv) < 3:
        print("Usage: python src/main.py <target_directory> <task_description>")
        sys.exit(1)
        
    target_dir = sys.argv[1]
    task = sys.argv[2]
    
    print(f"Target Directory: {target_dir}")
    print(f"Task: {task}")
    
    llm = LLMClient()
    controller = IterationController(target_dir, llm)
    
    controller.run(task)

if __name__ == "__main__":
    main()
