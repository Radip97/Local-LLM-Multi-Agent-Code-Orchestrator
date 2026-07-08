"""
src/core/llm.py
Lightweight OpenAI-compatible LLM client using standard library.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Optional
from src.core.config import LLM_BASE_URL, LLM_MODEL, LLM_API_KEY

class LLMClient:
    def __init__(self, base_url: str = None, model: str = None, api_key: str = None):
        # Default to LMStudio local endpoint
        self.base_url = base_url or LLM_BASE_URL or "http://localhost:1234/v1"
        self.model = model or LLM_MODEL or "unsloth/qwen3.5-9b"
        self.api_key = api_key or LLM_API_KEY or "lm-studio"

    def call(self, prompt: str, system_prompt: str = "You are a helpful coding assistant.") -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
        }
        
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req) as response:
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
