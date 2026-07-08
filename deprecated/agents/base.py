"""
agents/base.py
──────────────
BaseAgent — foundation class for all agents.

Wraps JSONForcedCaller so every agent gets:
  • Deterministic JSON tool-calling (model-agnostic)
  • Short/long-term memory access
  • Role-injected system prompt preamble
  • Image encoding for multimodal models
"""
from __future__ import annotations

import base64
import mimetypes
import os
import sys
from typing import Optional

from openai import OpenAI

import config
from core.json_caller import JSONForcedCaller, make_caller
from core.memory import LongTermMemory, ShortTermMemory
from core.tool_registry import ToolExecutor


class BaseAgent:
    """
    Base class for all agents in the orchestrator.

    Sub-classes must set:
        ROLE  — human-readable role label (e.g. "Developer")
        TOOLS — list of tool names this agent may call
    """

    ROLE:  str       = "Agent"
    TOOLS: list[str] = []

    def __init__(
        self,
        model_name: Optional[str] = None,
        stm: Optional[ShortTermMemory] = None,
        ltm: Optional[LongTermMemory] = None,
        executor_context: Optional[dict] = None,
        verbose: bool = False,
    ) -> None:
        self.model_name = model_name or config.DEVELOPER_MODEL
        self.stm = stm or ShortTermMemory()
        self.ltm = ltm
        self.verbose = verbose

        self.client = OpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)
        self._executor = ToolExecutor(context=executor_context or {})

        # Auto-detect model if not explicitly set
        self._resolved_model: Optional[str] = None

    # ── Model resolution ───────────────────────────────────────────────────────

    def get_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model
        if self.model_name:
            self._resolved_model = self.model_name
            return self._resolved_model

        try:
            models = [m.id for m in self.client.models.list().data
                      if "embed" not in m.id.lower()]
            if not models:
                raise RuntimeError("No models found at " + config.API_BASE_URL)
            # Smart mapping by role
            coders = [m for m in models if "coder" in m.lower()]
            if self.ROLE == "Planner" and len(coders) > 1:
                self._resolved_model = next(
                    (c for c in coders if "14b" in c.lower()), coders[0])
            elif self.ROLE == "QA":
                non_coders = [m for m in models if "coder" not in m.lower()]
                self._resolved_model = non_coders[0] if non_coders else models[0]
            elif coders:
                self._resolved_model = coders[0]
            else:
                self._resolved_model = models[0]
            return self._resolved_model
        except Exception as exc:
            print(f"[{self.ROLE}] Model auto-detect failed: {exc}", file=sys.stderr)
            sys.exit(1)

    # ── Executor context ───────────────────────────────────────────────────────

    def update_executor_context(self, **kwargs: str) -> None:
        """Inject or update context values (staging_dir, target_dir, etc.)."""
        for k, v in kwargs.items():
            self._executor.update_context(k, v)

    # ── Core invocation helpers ────────────────────────────────────────────────

    def _make_caller(self) -> JSONForcedCaller:
        return make_caller(
            client=self.client,
            model=self.get_model(),
            executor=self._executor,
            tool_names=self.TOOLS or None,
            verbose=self.verbose,
        )

    def run_with_tools(self, system_prompt: str, user_message: str) -> str:
        """
        Run the JSON-forced tool loop and return the final answer text.
        Logs tool activity to short-term memory.
        """
        caller = self._make_caller()
        result = caller.run(system_prompt, user_message)

        # Log tool activity to STM
        for record in caller.history:
            if record.parsed and not record.parsed.is_final and record.tool_result:
                self.stm.log_tool(
                    agent=self.ROLE,
                    tool=record.parsed.action,
                    args=record.parsed.args,
                    success=record.tool_result.success,
                    output_preview=record.tool_result.as_text(),
                )
                if not record.tool_result.success and self.ltm:
                    self.ltm.add_error_pattern(
                        agent=self.ROLE,
                        error=record.tool_result.error or "unknown",
                        context=f"tool={record.parsed.action} args={record.parsed.args}",
                    )

        return result

    def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = config.MODEL_TEMPERATURE,
    ) -> str:
        """Simple text-only LLM call (no tool loop)."""
        return self.call_llm_with_images(system_prompt, user_prompt, temperature, [])

    def call_llm_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = config.MODEL_TEMPERATURE,
        image_paths: Optional[list[str]] = None,
    ) -> str:
        """LLM call with optional base64-encoded images (multimodal)."""
        image_paths = image_paths or []
        user_content: object = user_prompt

        if image_paths:
            parts = [{"type": "text", "text": user_prompt}]
            for encoded in self._encode_images(image_paths):
                parts.append(encoded)
            user_content = parts

        try:
            resp = self.client.chat.completions.create(
                model=self.get_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
                top_p=config.MODEL_TOP_P,
                presence_penalty=config.MODEL_PRESENCE_PENALTY,
                extra_body={
                    "top_k": config.MODEL_TOP_K,
                    "min_p": config.MODEL_MIN_P,
                    "repetition_penalty": config.MODEL_REPETITION_PENALTY,
                },
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            raise RuntimeError(
                f"[{self.ROLE}] LLM call failed (model={self.get_model()}): {exc}"
            )

    # ── Image encoding ─────────────────────────────────────────────────────────

    @staticmethod
    def _encode_images(image_paths: list[str]) -> list[dict]:
        parts = []
        for path in image_paths:
            if not os.path.isfile(path):
                continue
            mime, _ = mimetypes.guess_type(path)
            if mime is None:
                ext_map = {
                    ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif",
                    ".webp": "image/webp",
                }
                mime = ext_map.get(os.path.splitext(path)[1].lower(), "image/jpeg")
            try:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            except OSError:
                continue
        return parts

    # ── Error pattern context ──────────────────────────────────────────────────

    def _error_context(self) -> str:
        if self.ltm:
            return self.ltm.error_pattern_summary()
        return ""
