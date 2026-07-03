import patch_env
import os

# API configuration
# For LM Studio, default is http://localhost:1234/v1
# For Ollama, default is http://localhost:11434/v1
# For llama.cpp, default is http://localhost:8080/v1
API_BASE_URL = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
API_KEY = os.environ.get("LOCAL_LLM_API_KEY", "lm-studio")

# Model configuration
# If set to None, the orchestrator will automatically list loaded models and map them
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "unsloth/qwen3.5-9b")
DEVELOPER_MODEL = os.environ.get("DEVELOPER_MODEL", "unsloth/qwen3.5-9b")
QA_MODEL = os.environ.get("QA_MODEL", "unsloth/qwen3.5-9b")

# Workflow loop configurations
MAX_PLAN_ITERATIONS = 5
MAX_CODE_ITERATIONS = 8

# File-watching or ignores (for reading current codebase workspace)
IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "artifacts",
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".zip",
    ".tar",
    ".gz",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".log",
    ".json",
    ".csv",
}
