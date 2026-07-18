"""
src/core/llm.py
Lightweight OpenAI-compatible LLM client using standard library.
Includes VRAM-aware model hot-swap: automatically ejects the current model
before loading the required one, so t/s never degrades from VRAM pressure.
"""

import json
import urllib.request
import urllib.error
from typing import Optional, List
from src.core.config import (
    LLM_BASE_URL, LLM_MODEL, LLM_API_KEY,
    LLM_LOAD_TIMEOUT, LLM_COMPLETIONS_TIMEOUT, LLM_META_TIMEOUT
)

# ── Internal base URL (shared by all helpers) ──────────────────────────────
_BASE_URL = LLM_BASE_URL or "http://localhost:1234"
_V1_URL   = f"{_BASE_URL}/v1"
_API_URL  = f"{_BASE_URL}/api/v1"


# ══════════════════════════════════════════════════════════════════════════════
# VRAM management helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_loaded_models() -> dict:
    """
    Return a dict mapping model_key → instance_id for every model
    currently loaded in VRAM.  The instance_id is required by the
    LM Studio /api/v1/models/unload endpoint.
    """
    url = f"{_API_URL}/models"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=LLM_META_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        loaded = {}
        for m in data.get("models", []):
            instances = m.get("loaded_instances", [])
            if instances:
                # instance is a dict with an 'id' key
                inst_id = instances[0].get("id", m["key"]) if isinstance(instances[0], dict) else m["key"]
                loaded[m["key"]] = inst_id
        return loaded
    except Exception as e:
        print(f"[LLM VRAM] Could not fetch model list: {e}")
        return {}


def _unload(instance_id: str) -> bool:
    """
    Send an unload request using the instance_id (NOT the model key).
    LM Studio's /api/v1/models/unload requires the 'instance_id' field.
    Returns True on success.
    """
    url = f"{_API_URL}/models/unload"
    payload = json.dumps({"instance_id": instance_id}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_LOAD_TIMEOUT) as resp:
            resp.read()
        print(f"[LLM VRAM] Ejected: {instance_id}")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        # 404 / model_not_found means it's already gone — treat as success
        if e.code == 404 or "model_not_found" in body:
            return True
        print(f"[LLM VRAM] Eject failed for {instance_id} (HTTP {e.code}): {body}")
        return False
    except Exception as e:
        print(f"[LLM VRAM] Eject error for {instance_id}: {e}")
        return False


def _load(model_key: str) -> bool:
    """Send a load request for a specific model key. Returns True on success."""
    url = f"{_API_URL}/models/load"
    payload = json.dumps({"model": model_key}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_LOAD_TIMEOUT) as resp:
            resp.read()
        print(f"[LLM VRAM] Loaded:  {model_key}")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"[LLM VRAM] Load failed for {model_key} (HTTP {e.code}): {body}")
        return False
    except Exception as e:
        print(f"[LLM VRAM] Load error for {model_key}: {e}")
        return False


def ensure_model_loaded(target_model: str) -> bool:
    """
    Core VRAM hot-swap routine.

    1. Check which models are currently in VRAM (key → instance_id map).
    2. If target_model is already loaded → nothing to do, return True.
    3. For every OTHER model found in VRAM → eject it by instance_id.
    4. Load target_model.

    This guarantees a single model occupies VRAM at any time, keeping
    t/s high and preventing OOM errors.
    """
    loaded = get_loaded_models()  # {model_key: instance_id}

    # Already in VRAM — skip the load/eject cycle
    if target_model in loaded:
        print(f"[LLM VRAM] {target_model} already in VRAM. Skipping swap.")
        return True

    # Eject everything else first, using their instance_id
    for model_key, instance_id in loaded.items():
        if model_key != target_model:
            _unload(instance_id)

    # Now load what we need
    return _load(target_model)


def release_model(model_key: str) -> bool:
    """
    Explicitly eject a model from VRAM when it is no longer needed.
    Call this after a coder/debugger turn finishes so VRAM is freed
    before the next model is loaded.
    """
    loaded = get_loaded_models()  # {model_key: instance_id}
    if model_key not in loaded:
        return True   # already gone
    return _unload(loaded[model_key])


# ══════════════════════════════════════════════════════════════════════════════
# LLM Client
# ══════════════════════════════════════════════════════════════════════════════

class LLMClient:
    def __init__(self, base_url: str = None, model: str = None, api_key: str = None):
        self.base_url = (base_url or _V1_URL).rstrip("/")
        self.model    = model or LLM_MODEL or "qwen3-14b"
        self.api_key  = api_key or LLM_API_KEY or "lm-studio"

    def call(self, prompt: str, system_prompt: str = "You are a helpful coding assistant.") -> str:
        """
        Ensure the correct model is loaded in VRAM, then call the chat
        completions endpoint.  The model swap happens transparently.
        """
        # ── VRAM swap before every call ──────────────────────────────────────
        ensure_model_loaded(self.model)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt}
            ],
            "temperature": 0.1,
        }

        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"),
            headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=LLM_COMPLETIONS_TIMEOUT) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                return response_data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"[LLM Client Error] HTTP {e.code}: {err_body}")
            return f"LLM_ERROR: {e.code} - {err_body}"
        except urllib.error.URLError as e:
            print(f"[LLM Client Error] Failed to connect to {url}: {e}")
            return f"LLM_ERROR: {e}"
        except Exception as e:
            print(f"[LLM Client Error] Unexpected error: {e}")
            return f"LLM_ERROR: {e}"
