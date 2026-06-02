import time
from typing import Any, Optional


class TTLCache:
    """In-memory key-value cache with per-entry expiry. Thread-safe for single-process use."""

    def __init__(self, default_ttl: int = 900):
        self._store: dict[str, tuple[Any, float]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self.default_ttl
        self._store[key] = (value, time.monotonic() + ttl)


# One shared instance for gas prices (state+grade → float)
price_cache = TTLCache()
