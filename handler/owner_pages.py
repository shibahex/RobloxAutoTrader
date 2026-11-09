"""
Remembers how far the owner scan got on each item, so the same owners
aren't read again. Saved in owner_scan_cache.json (shared by every account)
and forgotten after Remember Scanned Owners Days.
"""

import threading
import time

from handler.handle_json import JsonHandler

LOCK = threading.Lock()


class OwnerPages:
    FILE = "owner_scan_cache.json"

    def __init__(self, memory_days: float, clock=time.time, file: str = FILE):
        self.memory_seconds = (memory_days or 0) * 86400
        self.clock = clock
        self.json = JsonHandler(file)

    def _fresh(self, data: dict) -> dict:
        """The entries younger than the memory; older ones are dropped."""
        now = self.clock()
        return {
            item_id: entry
            for item_id, entry in data.items()
            if now - entry.get("started", 0) < self.memory_seconds
        }

    def start(self, item_id) -> str | None:
        """
        The page to carry on from: "" = the first page, None = every owner
        was already read (skip the item until it's forgotten).
        """
        if not self.memory_seconds:
            return ""
        with LOCK:
            entry = self._fresh(self.json.read_data()).get(str(item_id))
        if not entry:
            return ""
        return None if entry.get("done") else entry.get("cursor") or ""

    def done_items(self) -> set[str]:
        """Item ids whose every owner was read (skipped until forgotten)."""
        if not self.memory_seconds:
            return set()
        with LOCK:
            data = self._fresh(self.json.read_data())
        return {item_id for item_id, entry in data.items() if entry.get("done")}

    def save(self, item_id, cursor: str | None):
        """The next page to read. cursor None = every owner was read."""
        if not self.memory_seconds:
            return
        with LOCK:
            data = self._fresh(self.json.read_data())
            entry = data.get(str(item_id)) or {"started": self.clock()}
            entry.update(cursor=cursor, done=cursor is None)
            data[str(item_id)] = entry
            self.json.write_data(data)

    def forget(self, item_id):
        """Start the item over (e.g. Roblox stopped accepting its cursor)."""
        with LOCK:
            data = self._fresh(self.json.read_data())
            if data.pop(str(item_id), None) is not None:
                self.json.write_data(data)
