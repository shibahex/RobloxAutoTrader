"""
Remembers the counters each account sent, and how fast traders answered them,
so the bot can stop counter loops:
  - the same counter is never sent to a trader twice
  - after Max Counters Per Trader, their trades are declined instead
  - traders who answer instantly every time (likely bots) are declined too
Saved in counter_history.json, so it survives restarts.
"""

import json
import os
import threading
import time

FILE = "counter_history.json"
# Seconds Roblox's clock may be behind ours
CLOCK_SLACK = 30


def trade_signature(self_item_ids, their_item_ids, self_robux=0) -> str:
    """Same items (in any order) and Robux = same trade."""
    return json.dumps(
        [sorted(map(str, self_item_ids)), sorted(map(str, their_item_ids)), self_robux or 0]
    )


class CounterHistory:
    """
    {trader id: {"counters": [[sent at, signature]],
                 "replies": [[trade id, seconds after our last counter]]}}
    path None = kept in memory only (tests).
    """

    _lock = threading.Lock()

    def __init__(self, path=FILE, account_id="", memory_hours=24, clock=time.time):
        self.path = path
        self.account = str(account_id)
        self.memory_seconds = memory_hours * 3600
        self.clock = clock
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path or not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f).get(self.account, {})
        except (OSError, ValueError, AttributeError):
            return {}

    def _save(self):
        if not self.path:
            return
        with self._lock:
            try:
                with open(self.path, encoding="utf-8") as f:
                    everyone = json.load(f)
            except (OSError, ValueError):
                everyone = {}
            everyone[self.account] = self.data
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(everyone, f)
            os.replace(tmp, self.path)

    def _trader(self, trader) -> dict:
        """The trader's record, with entries older than the memory dropped."""
        record = self.data.setdefault(str(trader), {"counters": [], "replies": []})
        cutoff = self.clock() - self.memory_seconds
        record["counters"] = [c for c in record["counters"] if c[0] >= cutoff]
        if not record["counters"]:
            record["replies"] = []
        return record

    def record_counter(self, trader, signature):
        self._trader(trader)["counters"].append([self.clock(), signature])
        self._save()

    def sent(self, trader) -> set:
        """Signatures of the counters already sent to this trader."""
        return {signature for _, signature in self._trader(trader)["counters"]}

    def counters(self, trader) -> int:
        return len(self._trader(trader)["counters"])

    def note_inbound(self, trader, trade_id, created) -> float | None:
        """
        Records an inbound that came after one of our counters (a counter back)
        and returns how many seconds after our last counter it was made.
        None if it isn't a reply. Each trade is only counted once.
        """
        record = self._trader(trader)
        if not record["counters"] or created is None:
            return None
        for seen_id, seconds in record["replies"]:
            if seen_id == str(trade_id):
                return seconds
        last_counter = record["counters"][-1][0]
        # Roblox's clock and ours can differ by a few seconds
        if created < last_counter - CLOCK_SLACK:
            return None
        seconds = max(0.0, created - last_counter)
        record["replies"].append([str(trade_id), seconds])
        self._save()
        return seconds

    def instant_replies(self, trader, max_seconds) -> int:
        """How many of the trader's latest replies in a row were this fast."""
        streak = 0
        for _, seconds in reversed(self._trader(trader)["replies"]):
            if seconds > max_seconds:
                break
            streak += 1
        return streak
