[← Config guide](README.md)

# [Inbound Settings]

What to do with trades people send you. Checked every `Check Inbounds Every Minutes`.

| Setting | What it does |
|---|---|
| `Accept Valid Trades` | Accepts trades that pass your config. Off by default. |
| `Counter Trades` | Counters trades that aren't accepted, using a trade made from your config. |
| `Dont Counter Wins` | Leaves trades that are already a win in Overall Value alone instead of countering. |
| `Check Inbounds Every Minutes` | Minutes between checks. Missing, 0 or negative falls back to 30. |

## What gets accepted
A trade is accepted only if it:
- passes your **minimum** gains in [`[Trading Settings]`](trading-settings.md). Maximums and score % are ignored, because a bigger win is still a win.
- passes your [`[Filtering Items]`](filtering-items.md) rules for the items you'd receive.
- doesn't ask for your Robux.
- doesn't give you projected items.

Before accepting, it re-checks the prices of anything it hasn't looked at in the last 6 hours.

> [!CAUTION]
> Accepting can't be undone. Only turn on `Accept Valid Trades` once your minimum gains are where you want them. Loose minimums (like `Minimum Value Gain = 1`) will accept near-even trades.
