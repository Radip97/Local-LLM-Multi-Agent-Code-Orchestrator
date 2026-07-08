from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class JsonCache:
    """Small file-backed JSON cache keyed by file fingerprints."""

    def __init__(self, root: str, name: str = ".orchestrator_cache") -> None:
        self.root = Path(root)
        self.path = self.root / name
        self.path.mkdir(parents=True, exist_ok=True)

    def file_fingerprint(self, rel_path: str) -> str:
        full = self.root / rel_path
        stat = full.stat()
        h = hashlib.sha256()
        h.update(str(stat.st_mtime_ns).encode())
        h.update(str(stat.st_size).encode())
        return h.hexdigest()

    def read(self, key: str) -> Any | None:
        path = self.path / f"{self._safe_key(key)}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write(self, key: str, value: Any) -> None:
        path = self.path / f"{self._safe_key(key)}.json"
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _safe_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
