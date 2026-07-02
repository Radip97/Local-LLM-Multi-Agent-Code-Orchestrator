import sys
import types
import dataclasses

# Force stdout/stderr to use UTF-8 encoding to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 1. Patch missing UnionType (A | B) from types module
if not hasattr(types, "UnionType"):
    types.UnionType = type("UnionType", (), {})

# 2. Patch missing 'slots' and 'kw_only' in dataclasses
original_dataclass = dataclasses.dataclass

def patched_dataclass(*args, **kwargs):
    kwargs.pop('slots', None)
    kwargs.pop('kw_only', None)
    return original_dataclass(*args, **kwargs)

dataclasses.dataclass = patched_dataclass

# 3. Patch typing_inspection for function-based NewType in early Python 3.10 alphas
try:
    import typing_inspection.typing_objects
    typing_inspection.typing_objects.is_newtype = lambda obj, /: hasattr(obj, '__supertype__')
except ImportError:
    pass
