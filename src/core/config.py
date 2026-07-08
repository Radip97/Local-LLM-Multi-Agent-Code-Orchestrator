"""
src/core/config.py
Configuration variables for the Single-LLM autonomous agent.
"""

import os

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai") # openai, ollama, local
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5-9b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "") # e.g. for vLLM or Ollama

# Debugger / Critic Agent Configuration
LLM_DEBUGGER_MODEL = os.getenv("LLM_DEBUGGER_MODEL", "qwen2.5-coder-1.5b-instruct-128k")
LLM_DEBUGGER_BASE_URL = os.getenv("LLM_DEBUGGER_BASE_URL", "")

# Limits
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "10"))
MAX_TOKENS_PER_REQUEST = int(os.getenv("MAX_TOKENS_PER_REQUEST", "32000"))

# File exclusions
EXCLUDED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "build", "dist", ".idea", ".vscode"
}
EXCLUDED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".png", ".jpg", ".jpeg", ".zip", ".tar", ".gz", ".pdf"
}

# Cache Config
CACHE_DIR = os.getenv("CACHE_DIR", ".agent_cache")
