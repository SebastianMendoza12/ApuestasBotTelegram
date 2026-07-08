import json
import os
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours


class OddsCache:
    def __init__(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace(" ", "_")
        return CACHE_DIR / f"{safe_key}.json"

    def get(self, key: str) -> dict | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) > CACHE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return data.get("response")

    def set(self, key: str, response: dict) -> None:
        path = self._cache_path(key)
        data = {"timestamp": time.time(), "response": response}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def invalidate(self, key: str) -> None:
        path = self._cache_path(key)
        path.unlink(missing_ok=True)


cache = OddsCache()