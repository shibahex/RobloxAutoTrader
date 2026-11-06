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
| `Max Counters Per Trader` | The same counter is never sent to a trader twice. After this many counters to one trader (within `Counter Memory Hours`), their trades are declined instead of countered. A trade that passes `Accept Valid Trades` is still accepted. 0 = no limit. Default 3. |
| `Instant Reply Minutes` | A counter-back made within this many minutes of your counter counts as instant. Default 20. |
| `Instant Replies To Call It A Bot` | After this many instant counter-backs in a row, the trader is treated as a bot and declined instead of countered. 0 = off. Default 3. |
| `Counter Memory Hours` | How long the counters you sent and their replies are remembered (saved in `counter_history.json`). Default 24. |
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
