[← Config guide](README.md)

# Troubleshooting

## "Couldnt find valid_trades heres invalid trades reasons"
The bot checked every trade with that person and none passed [`[Trading Settings]`](trading-settings.md). The counts show which setting blocked them most:

| Reason | Setting to loosen |
|---|---|
| `rap_gain` | Minimum / Maximum RAP Gain |
| `value_gain` | Minimum / Maximum Value Gain |
| `overall_gain` | Minimum / Maximum Overall Value Gain |
| `algo_gain` | Minimum / Maximum Rap Algorithm Gain |
| `overall_close_percentage` | Min / Max Overall Value Score Percentage |
| `rap_close_percentage` | Min / Max RAP Score Percentage |
| `min_value_of_trade` | Minimum Value Sum Of Trade |
| `min_rap_of_trade` | Minimum Rap Sum Of Trade |

If one reason is far ahead every time, that setting is too strict for your inventory. If the counts are all small, your items are probably on trade hold or ruled out by [`[Filtering Items]`](filtering-items.md).

## The bot won't start after editing the config
The error lists every setting it couldn't read and what it should be, e.g.:
```
These config settings are invalid: [Filtering Items] Maximum Amount of Duplicate Items (must be a whole number)
```
Usually it's `None` or a decimal in a whole-number setting, or a typo.

## All my outbound trades got cancelled after a config change
Set `Keep Trades Sent Before Config Change = True` in [`[Outbound Settings]`](outbound-settings.md).
