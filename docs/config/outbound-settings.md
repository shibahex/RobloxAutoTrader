[← Config guide](README.md)

# [Outbound Settings]

When to cancel trades you've sent. They're checked every 30 minutes, and re-priced every ~2 minutes when Rolimons updates (without extra Roblox requests).

An outbound trade is cancelled when:
- it no longer passes your minimum gains, loosened by the offsets below;
- you'd receive a projected item;
- you'd end up with more duplicates than [`Maximum Amount of Duplicate Items`](filtering-items.md).

Maximums and score % aren't checked.

| Setting | What it does |
|---|---|
| `Outbound Minimum Gain Offset to Cancel` | Taken off `Minimum RAP Gain` and `Minimum Overall Value Gain`. Whole number. |
| `RAP Algorithm Gain Offset to Cancel` | Taken off `Minimum Rap Algorithm Gain`. Whole number. |
| `Keep Trades Sent Before Config Change` | `True` = changing your config doesn't cancel the trades you already sent. They're only cancelled if they turn into a loss (or would give you a projected item). `False` = they must pass your new settings too. Older configs call this `Only Cancel Losing Trades After Config Change`, which still works. |

**Offset example:** `Minimum RAP Gain = 600` and an offset of `200` means a trade is cancelled once its RAP gain drops under 400. The result never goes below 0 (unless your minimum is negative), so trades that turn into a loss always get cancelled.

Without `Keep Trades Sent Before Config Change`, making your config stricter cancels every outbound that doesn't meet the new settings.
