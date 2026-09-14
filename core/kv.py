"""Persistent JSON key-value store (Day 2 foundation).

Shared durability layer for feature state that must survive restarts:
missions, workflows, experiences, alerts, events, budgets, permissions,
device registries, etc. Atomic writes, thread-safe, never deletes data by
default (``delete`` is explicit and audited).

Contract used across Day 2 modules:

* ``KeyValueStore(path)`` — open/create a store.
* ``get(key, default=None)`` / ``set(key, value)`` / ``update(key, fn)``
* ``delete(key)`` -> bool (explicit only)
* ``keys(prefix=None)`` / ``as_dict()`` / ``flush()`` / ``replace(new)``
* values must be JSON-serialisable.
"""

import json
import os
import threading
import time


class KeyValueStore:

    def __init__(self, path="data/kv.json"):
        self.path = str(path)
        self._lock = threading.RLock()
        self._data = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                self._data = loaded
        except (OSError, ValueError):
            self._data = {}

    def _flush_locked(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self.path}.{time.time_ns()}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------
    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def get_missing(self, key):
        """Return (value, existed_bool) — useful before writing defaults."""
        with self._lock:
            return self._data.get(key), key in self._data

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self._flush_locked()
        return True

    def update(self, key, fn, default=None):
        """Atomically mutate the value at ``key`` via ``fn(old) -> new``."""
        with self._lock:
            old = self._data.get(key, default)
            new = fn(old)
            self._data[key] = new
            self._flush_locked()
            return new

    def delete(self, key):
        with self._lock:
            existed = key in self._data
            if existed:
                del self._data[key]
                self._flush_locked()
            return existed

    def keys(self, prefix=None):
        with self._lock:
            keys = sorted(self._data.keys())
        if prefix is None:
            return keys
        return [k for k in keys if k.startswith(prefix)]

    def as_dict(self):
        with self._lock:
            return dict(self._data)

    def size(self):
        with self._lock:
            return len(self._data)

    def flush(self):
        with self._lock:
            self._flush_locked()
        return True

    def replace(self, new_data):
        with self._lock:
            self._data = dict(new_data)
            self._flush_locked()
        return True


def kv_namespace(store, prefix):
    """Curried view over one key: (…) helpers keep callers terse."""
    def get(default=None):
        return store.get(prefix, default)
    def set(value):
        return store.set(prefix, value)
    def update(fn, default=None):
        return store.update(prefix, fn, default)
    return {"get": get, "set": set, "update": update}


__all__ = ["KeyValueStore", "kv_namespace"]