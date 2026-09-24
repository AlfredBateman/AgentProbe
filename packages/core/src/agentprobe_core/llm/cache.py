"""Disk cache for LLM responses, keyed by hash(model, messages, params). For development
(LLM_CACHE=1): re-running a suite replays answers instead of spending the daily quota.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    @staticmethod
    def key(**parts: Any) -> str:
        blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            value = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None  # a torn or corrupt entry is just a miss
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value), encoding="utf-8")
        os.replace(tmp, path)
