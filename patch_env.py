import sys
import types
import dataclasses
import typing
from typing import TypeVar, MutableMapping, Any, Callable, Awaitable, Mapping, Union
from contextlib import AbstractAsyncContextManager

# 1. Patch missing UnionType (A | B) from types module immediately
if not hasattr(types, "UnionType"):
    types.UnionType = type("UnionType", (), {})

# 2. Patch missing 'slots' and 'kw_only' in dataclasses
original_dataclass = dataclasses.dataclass

def patched_dataclass(*args, **kwargs):
    kwargs.pop('slots', None)
    kwargs.pop('kw_only', None)
    return original_dataclass(*args, **kwargs)

dataclasses.dataclass = patched_dataclass

# 3. Patch missing typing features in early Python 3.10 alphas
for attr in ("TypeGuard", "TypeAlias", "ParamSpec", "Concatenate"):
    if not hasattr(typing, attr):
        try:
            import typing_extensions
            setattr(typing, attr, getattr(typing_extensions, attr))
        except (ImportError, AttributeError):
            pass

# 4. Mock starlette.types to bypass collections.abc.Callable Union operator '|' limitations
class MockStarletteTypes:
    pass

types_mod = MockStarletteTypes()
types_mod.AppType = TypeVar("AppType")
types_mod.Scope = MutableMapping[str, Any]
types_mod.Message = MutableMapping[str, Any]
types_mod.Receive = Callable[[], Awaitable[types_mod.Message]]
types_mod.Send = Callable[[types_mod.Message], Awaitable[None]]
types_mod.ASGIApp = Callable[[types_mod.Scope, types_mod.Receive, types_mod.Send], Awaitable[None]]
types_mod.StatelessLifespan = Callable[[types_mod.AppType], AbstractAsyncContextManager[None]]
types_mod.StatefulLifespan = Callable[[types_mod.AppType], AbstractAsyncContextManager[Mapping[str, Any]]]
types_mod.Lifespan = Union[types_mod.StatelessLifespan[types_mod.AppType], types_mod.StatefulLifespan[types_mod.AppType]]

sys.modules["starlette.types"] = types_mod

# 5. Patch typing_inspection for function-based NewType in early Python 3.10 alphas
try:
    import typing_inspection.typing_objects
    typing_inspection.typing_objects.is_newtype = lambda obj, /: hasattr(obj, '__supertype__')
except ImportError:
    pass

# Force stdout/stderr to use UTF-8 encoding to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
