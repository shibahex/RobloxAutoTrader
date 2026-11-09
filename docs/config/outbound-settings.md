[← Config guide](README.md)

# [Outbounds]

When to cancel trades you've sent. They're checked every 30 minutes, and re-priced every ~2 minutes when Rolimons updates (without extra Roblox requests).

An outbound trade is cancelled when:
- it no longer passes your minimum gains, loosened by the offsets below;
- an item you'd receive (or send) becomes projected, if the settings below say so;
- you'd end up with more duplicates than [`Max Duplicates Owned`](filtering-items.md).

Maximums and score % aren't checked.

| Setting | What it does |
|---|---|
| `Overall And RAP Cancel Offset` | How far a sent trade's profit can drop below `Min RAP Profit` and `Min Overall Profit` before it's cancelled. Between 0 and 1 = a share of the minimum (`0.02` = 2% under it); otherwise Robux. |
| `Algorithm Cancel Offset` | Same, for `Min Algorithm Profit`. |
| `Keep Trades On Config Change` | `True` = changing your config doesn't cancel the trades you already sent. They're only cancelled if they turn into a loss (or would give you a projected item). `False` = they must pass your new settings too. Older configs call this `Only Cancel Losing Trades After Config Change`, which still works. |
| `Cancel If Receiving Projected` | `True` (default) = cancel when an item you'd receive becomes projected. `False` = keep judging the trade like any other; the RAP algorithm value already ignores a pushed-up RAP. |
| `Cancel If Sending Projected` | `True` = cancel when an item you're sending becomes projected. Default `False`. |

**Offset example:** with `Min RAP Profit = 600`, an offset of `200` cancels a trade once its RAP profit drops under 400, and an offset of `0.02` cancels it under 588 (2% under the minimum). The result never goes below 0 (unless your minimum is negative), so trades that turn into a loss always get cancelled.

Without `Keep Trades On Config Change`, making your config stricter cancels every outbound that doesn't meet the new settings.
