[← Config guide](README.md)

# [Inbound Settings]

What to do with trades people send you. Checked every `Check Inbounds Every Minutes`.

| Setting | What it does |
|---|---|
| `Accept Valid Trades` | Accepts trades that pass your config. Off by default. |
| `Minimum/Maximum ... Gain` | RAP, Value, Overall Value and Rap Algorithm gains for inbounds, used to accept and to counter. They replace the `[Trading Settings]` gains (and account configs') for inbounds. A missing line uses the `[Trading Settings]` one. Accepting ignores the maximums. |
| `Counter Trades` | Counters trades that aren't accepted. The counter keeps as much of their trade as it can, changing as few items as possible to pass your inbound gains. |
| `Dont Counter Wins` | Leaves trades that are already a win in Overall Value alone instead of countering. |
| `Decline If No Counter` | When no counter passes your config, declines the trade (needs `Counter Trades`). False leaves it in your inbounds to be tried again next check. Missing counts as True. |
| `Check Inbounds Every Minutes` | Minutes between checks. Missing, 0 or negative falls back to 30. |

## What gets accepted
A trade is accepted only if it:
- passes your **minimum** inbound gains (above; any not set come from [`[Trading Settings]`](trading-settings.md)). Maximums and score % are ignored, because a bigger win is still a win.
- passes your [`[Filtering Items]`](filtering-items.md) rules for the items you'd receive.
- doesn't ask for your Robux.
- doesn't give you projected items.

Before accepting, it re-checks the prices of anything it hasn't looked at in the last 6 hours.

> [!CAUTION]
> Accepting can't be undone. Only turn on `Accept Valid Trades` once your minimum gains are where you want them. Loose minimums (like `Minimum Value Gain = 1`) will accept near-even trades.
