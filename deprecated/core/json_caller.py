"""
core/json_caller.py
────────────────────
Hybrid tool-calling engine: tries native OpenAI function calling first,
auto-detects support on the first round, then falls back to JSON-prompt
injection if the model doesn't return tool_calls.

Detection logic
───────────────
Round 1 is ALWAYS sent with the native OpenAI `tools` parameter.
• If the model returns tool_calls → native confirmed, stays native.
• If the model returns no tool_calls on round 1 → JSON-prompt fallback.

This means Qwen/Llama/DeepSeek models that don't support native function
calling will silently get the JSON-prompt protocol on their second chance,
while models like GPT-4o or any OpenAI-compatible server that does support
it get the cleaner native path with zero overhead.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import OpenAI

import config
from core.tool_registry import ToolExecutor, ToolRegistry, ToolResult

# ── Tunable limits ─────────────────────────────────────────────────────────────
MAX_JSON_RETRIES  = 3
MAX_AGENT_ROUNDS  = 20
FINAL_ACTION      = "final_answer"

# ── Calling modes ──────────────────────────────────────────────────────────────
MODE_UNKNOWN      = "unknown"
MODE_NATIVE       = "native"
MODE_JSON_PROMPT  = "json_prompt"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class AgentAction:
    action: str
    args: dict[str, Any]

    @property
    def is_final(self) -> bool:
        return self.action == FINAL_ACTION

    @property
    def result_text(self) -> str:
        return self.args.get("result", "")


@dataclass
class RoundRecord:
    round_num:    int
    raw_response: str
    parsed:       Optional[AgentAction]
    tool_result:  Optional[ToolResult]
    mode:         str = MODE_UNKNOWN
    json_retries: int = 0


# ── Protocol injection block (JSON-prompt fallback) ────────────────────────────

_PROTOCOL_HEADER = """
╔══════════════════════════════════════════════════════════════════╗
║  TOOL-CALLING PROTOCOL  —  READ CAREFULLY BEFORE RESPONDING     ║
╠══════════════════════════════════════════════════════════════════╣
║  Every response you give MUST be a SINGLE valid JSON object.    ║
║  No prose, no markdown, no code fences — just raw JSON.         ║
║                                                                  ║
║  FORMAT A — call a tool:                                         ║
║    {{"action": "<tool_name>", "args": {{...}}}}                  ║
║                                                                  ║
║  FORMAT B — you are finished, provide your final answer:         ║
║    {{"action": "final_answer", "args": {{"result": "..."}}}}     ║
║                                                                  ║
║  Rules:                                                          ║
║  • Output ONLY the JSON — nothing before or after it.           ║
║  • "action" must match one of the tools listed below, or be     ║
║    "final_answer" when done.                                     ║
║  • "args" must be a JSON object ({{}} is valid for no args).     ║
║  • One JSON object per response — never multiple objects.        ║
╚══════════════════════════════════════════════════════════════════╝

AVAILABLE TOOLS:
{tool_schema}
"""

_JSON_RETRY_MSG = (
    "⚠️  Your last response was NOT valid JSON. You MUST reply with ONLY one of:\n"
    '  {{"action": "tool_name", "args": {{...}}}}\n'
    '  {{"action": "final_answer", "args": {{"result": "your answer"}}}}\n'
    "No explanation, no markdown — only the JSON object."
)


# ── JSON parser (4 strategies) ─────────────────────────────────────────────────

def _parse_action(raw: str) -> Optional[AgentAction]:
    """Extract an AgentAction from model text output."""
    text = raw.strip()

    def _try(s: str) -> Optional[AgentAction]:
        try:
            s = re.sub(r"^```(?:json)?\s*", "", s.strip())
            s = re.sub(r"\s*```$", "", s.strip())
            data = json.loads(s)
            if isinstance(data, dict) and "action" in data and "args" in data:
                return AgentAction(action=str(data["action"]), args=dict(data.get("args") or {}))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return None

    # 1. Whole text
    r = _try(text)
    if r:
        return r

    # 2. Inside ``` fences
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.DOTALL)
    if m:
        r = _try(m.group(1))
        if r:
            return r

    # 3. First {...} containing "action"
    m = re.search(r'(\{[^{}]*"action"[^{}]*\})', text, re.DOTALL)
    if m:
        r = _try(m.group(1))
        if r:
            return r

    # 4. Outermost balanced braces
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                r = _try(text[start: i + 1])
                if r:
                    return r
                break

    return None


def _build_native_tools_schema(tool_names: Optional[list[str]] = None) -> list[dict]:
    """Return OpenAI-format tools array for the given (or all) tools."""
    schemas = []
    for name, defn in (
        (n, d) for n, d in vars(ToolRegistry).items()
        if False  # we pull from _REGISTRY below
    ):
        pass

    from core.tool_registry import _REGISTRY
    for name, defn in _REGISTRY.items():
        if tool_names is not None and name not in tool_names:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": defn.name,
                "description": defn.description,
                "parameters": defn.parameters,
            },
        })

    # Always add final_answer as a tool for native mode
    schemas.append({
        "type": "function",
        "function": {
            "name": FINAL_ACTION,
            "description": "Call this when you are done and want to return your final answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {
                        "type": "string",
                        "description": "Your complete final answer or summary.",
                    }
                },
                "required": ["result"],
            },
        },
    })
    return schemas


# ── Main caller ────────────────────────────────────────────────────────────────

class JSONForcedCaller:
    """
    Hybrid tool-calling engine with native-first detection.

    Round 1 always uses native function calling. If the model responds with
    tool_calls → native mode is locked in. Otherwise the caller falls back
    to JSON-prompt injection for all remaining rounds.
    """

    def __init__(
        self,
        client: OpenAI,
        model: str,
        executor: ToolExecutor,
        tool_names: Optional[list[str]] = None,
        max_rounds: int = MAX_AGENT_ROUNDS,
        max_json_retries: int = MAX_JSON_RETRIES,
        temperature: float = 0.2,
        top_p: float = 0.95,
        presence_penalty: float = 0.0,
        extra_body: Optional[dict] = None,
        verbose: bool = False,
    ) -> None:
        self._client      = client
        self._model       = model
        self._executor    = executor
        self._tool_names  = tool_names
        self._max_rounds  = max_rounds
        self._max_retries = max_json_retries
        self._temperature = temperature
        self._top_p       = top_p
        self._presence_penalty = presence_penalty
        self._extra_body  = extra_body or {}
        self._verbose     = verbose
        self._mode        = MODE_UNKNOWN   # detected on first call
        self.history: list[RoundRecord] = []

    # ── Public ─────────────────────────────────────────────────────────────────

    def run(self, system_prompt: str, user_message: str) -> str:
        """Execute the agent loop. Returns the final answer text."""
        native_schema = _build_native_tools_schema(self._tool_names)

        # Messages for native path (clean system prompt)
        native_messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]

        # Round 1 — always native first
        raw, tool_calls_native = self._native_call(native_messages, native_schema)

        if self._verbose:
            print(f"\n[Round 1 | native probe] {raw[:200]}", file=sys.stderr)
            print(f"  tool_calls returned: {bool(tool_calls_native)}", file=sys.stderr)

        if tool_calls_native:
            # ── Native confirmed ──────────────────────────────────────────────
            self._mode = MODE_NATIVE
            if self._verbose:
                print("  → Mode locked: NATIVE", file=sys.stderr)
            return self._loop_native(native_messages, raw, tool_calls_native, native_schema)
        else:
            # ── No tool_calls returned — switch to JSON prompt ────────────────
            self._mode = MODE_JSON_PROMPT
            if self._verbose:
                print("  → No tool_calls detected. Mode: JSON_PROMPT", file=sys.stderr)

            # Re-run round 1 with JSON-prompt protocol injected
            json_system = system_prompt + _PROTOCOL_HEADER.format(
                tool_schema=ToolRegistry.schema_block(self._tool_names)
            )
            json_messages: list[dict] = [
                {"role": "system", "content": json_system},
                {"role": "user",   "content": user_message},
            ]
            return self._loop_json_prompt(json_messages)

    # ── Native loop ─────────────────────────────────────────────────────────────

    def _loop_native(
        self,
        messages: list[dict],
        first_raw: str,
        first_tool_calls: list,
        native_schema: list[dict],
    ) -> str:
        """Process tool_calls returned by the model using native function calling."""
        raw        = first_raw
        tool_calls = first_tool_calls

        for round_num in range(1, self._max_rounds + 1):
            # Append assistant message with tool_calls
            assistant_msg: dict = {"role": "assistant", "content": raw or ""}
            # Reconstruct tool_calls for the message history
            reconstructed = [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
            assistant_msg["tool_calls"] = reconstructed
            messages.append(assistant_msg)

            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                if fn_name == FINAL_ACTION:
                    self.history.append(RoundRecord(
                        round_num=round_num, raw_response=raw,
                        parsed=AgentAction(FINAL_ACTION, args),
                        tool_result=None, mode=MODE_NATIVE,
                    ))
                    return args.get("result", raw)

                tool_result = self._executor.execute(fn_name, args)
                self.history.append(RoundRecord(
                    round_num=round_num, raw_response=raw,
                    parsed=AgentAction(fn_name, args),
                    tool_result=tool_result, mode=MODE_NATIVE,
                ))

                if self._verbose:
                    icon = "✓" if tool_result.success else "✗"
                    print(
                        f"  {icon} [native] {fn_name}({args}) → "
                        f"{tool_result.as_text()[:120]}",
                        file=sys.stderr,
                    )

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      tool_result.as_text()[:4000],
                })

            # Next round
            raw, tool_calls = self._native_call(messages, native_schema)
            if self._verbose:
                print(f"\n[Round {round_num + 1} | native] {raw[:200]}", file=sys.stderr)

            if not tool_calls:
                # Model is done — content is the final answer
                return raw or self._best_fallback(messages)

        return self._best_fallback(messages)

    # ── JSON-prompt loop ────────────────────────────────────────────────────────

    def _loop_json_prompt(self, messages: list[dict]) -> str:
        json_fail_streak = 0

        for round_num in range(1, self._max_rounds + 1):
            raw = self._plain_call(messages)
            if self._verbose:
                print(f"\n[Round {round_num} | json_prompt] {raw[:200]}", file=sys.stderr)

            action = _parse_action(raw)

            if action is None:
                json_fail_streak += 1
                self.history.append(RoundRecord(
                    round_num=round_num, raw_response=raw,
                    parsed=None, tool_result=None,
                    mode=MODE_JSON_PROMPT, json_retries=json_fail_streak,
                ))
                if json_fail_streak >= self._max_retries:
                    return self._best_fallback(messages, raw)
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user",      "content": _JSON_RETRY_MSG})
                continue

            json_fail_streak = 0

            if action.is_final:
                self.history.append(RoundRecord(
                    round_num=round_num, raw_response=raw,
                    parsed=action, tool_result=None, mode=MODE_JSON_PROMPT,
                ))
                return action.result_text

            tool_result = self._executor.execute(action.action, action.args)
            self.history.append(RoundRecord(
                round_num=round_num, raw_response=raw,
                parsed=action, tool_result=tool_result, mode=MODE_JSON_PROMPT,
            ))

            if self._verbose:
                icon = "✓" if tool_result.success else "✗"
                print(
                    f"  {icon} [json] {action.action}({action.args}) → "
                    f"{tool_result.as_text()[:120]}",
                    file=sys.stderr,
                )

            messages.append({"role": "assistant", "content": raw})
            result_json = json.dumps({
                "tool":    action.action,
                "success": tool_result.success,
                "output":  tool_result.as_text()[:4000],
            })
            messages.append({"role": "user", "content": result_json})

        return self._best_fallback(messages)

    # ── LLM primitives ──────────────────────────────────────────────────────────

    def _native_call(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list]:
        """Make a native tool-calling request. Returns (content, tool_calls)."""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=self._temperature,
                top_p=self._top_p,
                presence_penalty=self._presence_penalty,
                extra_body=self._extra_body,
            )
            msg        = resp.choices[0].message
            content    = (msg.content or "").strip()
            tool_calls = msg.tool_calls or []
            return content, tool_calls
        except Exception as exc:
            if self._verbose:
                print(f"  [native_call error] {exc}", file=sys.stderr)
            return "", []

    def _plain_call(self, messages: list[dict]) -> str:
        """Plain text call (no tools parameter)."""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                top_p=self._top_p,
                presence_penalty=self._presence_penalty,
                extra_body=self._extra_body,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            return json.dumps({
                "action": FINAL_ACTION,
                "args":   {"result": f"LLM error: {exc}"},
            })

    @staticmethod
    def _best_fallback(messages: list[dict], last_raw: str = "") -> str:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                c = (msg.get("content") or "").strip()
                if c and not c.startswith("{"):
                    return c
        return last_raw or "(Agent produced no final answer)"

    @property
    def detected_mode(self) -> str:
        return self._mode


# ── Factory ────────────────────────────────────────────────────────────────────

def make_caller(
    client: OpenAI,
    model: str,
    executor: ToolExecutor,
    tool_names: Optional[list[str]] = None,
    temperature: float = config.MODEL_TEMPERATURE,
    verbose: bool = False,
) -> JSONForcedCaller:
    extra_body = {
        "top_k": config.MODEL_TOP_K,
        "min_p": config.MODEL_MIN_P,
        "repetition_penalty": config.MODEL_REPETITION_PENALTY,
    }
    return JSONForcedCaller(
        client=client,
        model=model,
        executor=executor,
        tool_names=tool_names,
        temperature=temperature,
        top_p=config.MODEL_TOP_P,
        presence_penalty=config.MODEL_PRESENCE_PENALTY,
        extra_body=extra_body,
        verbose=verbose,
    )
