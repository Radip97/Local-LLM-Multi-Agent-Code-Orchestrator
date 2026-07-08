"""
core/tool_registry.py
─────────────────────
@tool decorator, ToolDefinition, ToolResult, ToolRegistry, ToolExecutor.

Every tool is a plain Python function decorated with @tool. The decorator
auto-generates an OpenAI-compatible JSON schema from type hints and docstring,
and registers the function in the global registry so the JSON caller can
enumerate available tools and dispatch calls by name.
"""
from __future__ import annotations

import inspect
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

# ── Global registry ────────────────────────────────────────────────────────────
_REGISTRY: dict[str, "ToolDefinition"] = {}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Returned by every tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None

    def as_text(self) -> str:
        if self.success:
            out = self.output
            if isinstance(out, str):
                return out
            import json
            try:
                return json.dumps(out, ensure_ascii=False)
            except Exception:
                return str(out)
        return f"ERROR: {self.error}"


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict          # OpenAI-compatible parameter schema
    func: Callable
    required: list[str] = field(default_factory=list)


# ── Type-hint → JSON schema ────────────────────────────────────────────────────

def _to_json_type(annotation: Any) -> dict:
    """Convert a Python type annotation to a minimal JSON schema fragment."""
    import typing

    origin = getattr(annotation, "__origin__", None)

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is list or origin is list:
        args = getattr(annotation, "__args__", None)
        if args:
            return {"type": "array", "items": _to_json_type(args[0])}
        return {"type": "array"}
    if annotation is dict or origin is dict:
        return {"type": "object"}

    # Optional[X]  →  Union[X, None]
    if origin is getattr(typing, "Union", None):
        inner = [a for a in annotation.__args__ if a is not type(None)]
        if len(inner) == 1:
            return _to_json_type(inner[0])

    return {"type": "string"}  # safe fallback


def _build_schema(func: Callable) -> tuple[dict, list[str]]:
    """Return (parameters_schema, required_list) for an OpenAI function definition."""
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    sig = inspect.signature(func)
    props: dict = {}
    required: list[str] = []

    # Extract per-param docs from the docstring (Google style: "name: desc")
    doc = func.__doc__ or ""
    param_docs: dict[str, str] = {}
    for line in doc.splitlines():
        line = line.strip()
        for p_name in sig.parameters:
            if line.startswith(f"{p_name}:"):
                param_docs[p_name] = line.split(":", 1)[1].strip()

    SKIP = {"self", "cls", "staging_dir", "target_dir", "memory"}

    for p_name, param in sig.parameters.items():
        if p_name in SKIP:
            continue
        ann = hints.get(p_name, str)
        schema = _to_json_type(ann)
        schema["description"] = param_docs.get(p_name, f"Parameter '{p_name}'")
        props[p_name] = schema
        if param.default is inspect.Parameter.empty:
            required.append(p_name)

    parameters = {"type": "object", "properties": props}
    if required:
        parameters["required"] = required

    return parameters, required


# ── Decorator ──────────────────────────────────────────────────────────────────

def tool(name: str, description: str):
    """
    Decorator that registers a function as an agent-callable tool.

    Usage::

        @tool(name="read_file", description="Read a file's contents.")
        def read_file(path: str) -> ToolResult:
            ...
    """
    def decorator(func: Callable) -> Callable:
        parameters, required = _build_schema(func)
        _REGISTRY[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
            required=required,
        )
        func._tool_name = name  # type: ignore[attr-defined]
        return func

    return decorator


# ── Registry ───────────────────────────────────────────────────────────────────

class ToolRegistry:
    """Static access point for all registered tools."""

    @staticmethod
    def get(name: str) -> Optional[ToolDefinition]:
        return _REGISTRY.get(name)

    @staticmethod
    def all_names() -> list[str]:
        return list(_REGISTRY.keys())

    @staticmethod
    def subset(names: list[str]) -> list[ToolDefinition]:
        return [_REGISTRY[n] for n in names if n in _REGISTRY]

    @staticmethod
    def schema_block(names: Optional[list[str]] = None) -> str:
        """
        Return a compact, human-readable tool reference block to embed in
        system prompts (used by the JSON-forced caller).
        """
        import json
        lines: list[str] = []
        for name, defn in _REGISTRY.items():
            if names is not None and name not in names:
                continue
            props = defn.parameters.get("properties", {})
            param_str = json.dumps(
                {k: v.get("description", "") for k, v in props.items()},
                ensure_ascii=False,
            )
            lines.append(f'  "{name}": {{"desc": "{defn.description}", "args": {param_str}}}')
        return "{\n" + ",\n".join(lines) + "\n}"


# ── Executor ───────────────────────────────────────────────────────────────────

class ToolExecutor:
    """
    Executes a registered tool by name, injecting context kwargs
    (staging_dir, target_dir, etc.) that the function signature accepts.
    """

    def __init__(self, context: Optional[dict] = None):
        self._ctx = context or {}

    def update_context(self, key: str, value: Any) -> None:
        self._ctx[key] = value

    def execute(self, tool_name: str, args: dict) -> ToolResult:
        defn = ToolRegistry.get(tool_name)
        if not defn:
            available = ", ".join(ToolRegistry.all_names()) or "(none registered)"
            return ToolResult(
                success=False, output=None,
                error=f"Unknown tool '{tool_name}'. Available: {available}",
            )

        sig = inspect.signature(defn.func)
        injected = {k: v for k, v in self._ctx.items() if k in sig.parameters}

        # Strip args not accepted by the function (safety)
        accepted = {
            k: args[k] for k in args
            if k in sig.parameters and k not in injected
        }

        try:
            result = defn.func(**accepted, **injected)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, output=result)
        except Exception as exc:
            return ToolResult(
                success=False, output=None,
                error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}",
            )
