import patch_env  # noqa: F401  (Python 3.10 alpha patches)
import os

# ── LLM Server ──────────────────────────────────────────────────────────────
# LM Studio:  http://localhost:1234/v1
# Ollama:     http://localhost:11434/v1
# llama.cpp:  http://localhost:8080/v1
API_BASE_URL = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
API_KEY      = os.environ.get("LOCAL_LLM_API_KEY",  "lm-studio")

# ── Model assignment ─────────────────────────────────────────────────────────
# Set to None to auto-detect from the server's loaded models.
PLANNER_MODEL   = os.environ.get("PLANNER_MODEL",   "unsloth/qwen3.5-9b")
DEVELOPER_MODEL = os.environ.get("DEVELOPER_MODEL", "unsloth/qwen3.5-9b")
QA_MODEL        = os.environ.get("QA_MODEL",        "unsloth/qwen3.5-9b")
DEBUGGER_MODEL  = os.environ.get("DEBUGGER_MODEL",  "qwen2.5-coder-1.5b-instruct-128k")

# ── Generation settings ─────────────────────────────────────────────────────
# Qwen thinking-mode defaults for precise coding/web-dev tasks.
MODEL_TEMPERATURE        = float(os.environ.get("MODEL_TEMPERATURE", "0.6"))
MODEL_TOP_P              = float(os.environ.get("MODEL_TOP_P", "0.95"))
MODEL_TOP_K              = int(os.environ.get("MODEL_TOP_K", "20"))
MODEL_MIN_P              = float(os.environ.get("MODEL_MIN_P", "0.0"))
MODEL_PRESENCE_PENALTY   = float(os.environ.get("MODEL_PRESENCE_PENALTY", "0.0"))
MODEL_REPETITION_PENALTY = float(os.environ.get("MODEL_REPETITION_PENALTY", "1.0"))

# ── Workflow limits ──────────────────────────────────────────────────────────
MAX_PLAN_ITERATIONS = 5     # max planner → QA cycles before aborting
MAX_CODE_ITERATIONS = 8     # max developer → QA cycles per step

# ── File scanning ────────────────────────────────────────────────────────────
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "dist", "build", "artifacts", ".staging",
}

IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".zip", ".tar", ".gz",
    ".pdf", ".woff", ".woff2", ".ttf", ".eot",
    ".log", ".json", ".csv",
}
