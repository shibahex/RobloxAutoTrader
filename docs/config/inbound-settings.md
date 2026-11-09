[← Config guide](README.md)

# [Inbounds]

What to do with trades people send you. Checked every `Check Every Minutes`.

| Setting | What it does |
|---|---|
| `Accept Good Trades` | Accepts trades that pass your config. Off by default. |
| `Min/Max ... Profit` | RAP, Value, Overall and Algorithm profit for inbounds, used to accept and to counter. They replace the `[Profit]` ones (and account configs') for inbounds. A missing line uses the `[Profit]` one. Accepting ignores the maximums. |
| `Max Duplicates Owned` | Extra copies of an item you're allowed to own, for trades people send you (accepting and countering). Replaces the [Items] one for inbounds. 2 = you can own up to 3. Default 2. |
| `Max Duplicates From Trader` | Extra copies of the same item you'll take from the person who sent the trade. 2 = up to 3 of one item. Default 2. |
| `Counter` | Counters trades that aren't accepted. The counter keeps as much of their trade as it can, changing as few items as possible to pass your inbound gains. |
| `Skip Countering Wins` | Leaves trades that are already a win in Overall Value alone instead of countering. |
| `Decline If No Counter` | When no counter passes your config, declines the trade (needs `Counter`). False leaves it in your inbounds to be tried again next check. Missing counts as True. |
| `Max Counters Per Trader` | The same counter is never sent to a trader twice. After this many counters to one trader (within `Counter Memory Hours`), their trades are declined instead of countered. A trade that passes `Accept Good Trades` is still accepted. 0 = no limit. Default 3. |
| `Bot Reply Minutes` | A counter-back made within this many minutes of your counter counts as instant. Default 20. |
| `Bot Replies` | After this many instant counter-backs in a row, the trader is treated as a bot and declined instead of countered. 0 = off. Default 3. |
| `Counter Memory Hours` | How long the counters you sent and their replies are remembered (saved in `counter_history.json`). Default 24. |
| `Check Every Minutes` | Minutes between checks. Missing, 0 or negative falls back to 30. |

## What gets accepted
A trade is accepted only if it:
- passes your **minimum** inbound gains (above; any not set come from [`[Profit]`](trading-settings.md)). Maximums and score % are ignored, because a bigger win is still a win.
- passes your [`[Items]`](filtering-items.md) rules for the items you'd receive.
- doesn't ask for your Robux.
- doesn't give you projected items.

Before accepting, it re-checks the prices of anything it hasn't looked at in the last 6 hours.

It checks all your inbounds first, then accepts the ones that pass biggest overall win first. Accepting a trade usually breaks your other inbounds that asked for the same items, so the best one goes through and the rest are skipped. Items you just received count toward `Max Duplicates Owned` for the next trade.

> [!CAUTION]
> Accepting can't be undone. Only turn on `Accept Good Trades` once your minimum gains are where you want them. Loose minimums (like `Minimum Value Gain = 1`) will accept near-even trades.
