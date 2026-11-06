[← Config guide](README.md)

# [Filtering Generated Trades]

How long the bot searches, and which trade it picks when several pass.

| Setting | What it does |
|---|---|
| `Max Seconds Spent on One User` | If an account hasn't sent a trade in this many seconds, move on to your next account. |
| `Max Seconds Spent on Generating Trades` | Time limit for finding a trade with one person. When time's up, it picks from what it found, or moves on if it found nothing. |
| `Max Valid Trades` | Stop searching once more than this many trades pass, then pick one. `None` = keep searching until the time limit. Lower is faster. |
| `Select Trade Using` | Which passing trade gets sent. See below. |
| `Outbound Variety` | Spreads your items across your outbounds. `0` = off, `1` = strongest. See below. |

## How the search works
It goes through your items one at a time, then in pairs, then threes, and so on, and tries each against every combination of theirs. With big inventories it can run out of time before reaching the bigger combinations. Raising the time limit checks more; setting `Max Valid Trades` makes it stop as soon as it has enough to choose from.

## `Select Trade Using` options
"Gain" means what you get minus what you give.

| Option | Picks the trade with |
|---|---|
| `lowest_rap_gain` / `highest_rap_gain` | Smallest / biggest RAP gain |
| `lowest_value_gain` / `highest_value_gain` | Smallest / biggest Value gain |
| `lowest_overall_gain` / `highest_overall_gain` | Smallest / biggest Overall Value gain |
| `lowest_algo_gain` / `highest_algo_gain` | Smallest / biggest RAP Algorithm gain |
| `closest_score_based_on_overall_value` | The most even trade by Overall Value |
| `closest_score_based_on_rap` | The most even trade by RAP |
| `lowest_sum_of_trade_value` / `highest_sum_of_trade_value` | Smallest / biggest trade by total Value |
| `lowest_sum_of_trade_rap` / `highest_sum_of_trade_rap` | Smallest / biggest trade by total RAP |
| `lowest_sum_of_overall_value` / `highest_sum_of_overall_value` | Smallest / biggest trade by total Overall Value |
| `lowest_demand` / `highest_demand` | Lowest / highest Rolimons demand of all items added up |
| `lowest_volume_gain` / `highest_volume_gain` | Daily sales you get minus daily sales you give |
| `lowest_sum_of_volume` / `highest_sum_of_volume` | Daily sales of all items added up |
| `upgrade` | You give more items than you get |
| `downgrade` | You get more items than you give |
| `random` | Any of them |

The "lowest gain" options send trades that are still wins but closer to fair, which people accept more often. The "highest gain" options win more per trade but get declined more. An invalid option falls back to `lowest_rap_gain` with a warning.

## Outbound Variety
Every outbound that offers the same item of yours dies when one of them is accepted, since you no longer have the item. With about 100 trades a day, that's a lot of wasted sends.

Before picking, the bot counts how many of your open outbounds each of your items is already in, and adds that up for each passing trade. `Outbound Variety` drops the trades with the highest count:

| Value | What's kept |
|---|---|
| `0` | Everything (off) |
| `0.5` | Trades in the lower half of the range, e.g. if counts run from 0 to 10, trades with 5 or less |
| `1` | Only the trades with the lowest count |

`Select Trade Using` then picks from what's left, so higher values trade a little of that choice for variety. Counter trades use it too.

Counts come from the last outbound check (every 30 minutes) plus the trades sent since. With `Dont Check Outbounds = True` it only knows what it sent in the last day. Missing = `0`.

