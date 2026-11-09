[← Config guide](README.md)

# Troubleshooting

## "Couldnt find valid_trades heres invalid trades reasons"
The bot checked every trade with that person and none passed [`[Profit]`](trading-settings.md). The counts show which setting blocked them most:

| Reason | Setting to loosen |
|---|---|
| `rap_gain` | Minimum / Max RAP Profit |
| `value_gain` | Minimum / Max Value Profit |
| `overall_gain` | Minimum / Max Overall Profit |
| `algo_gain` | Minimum / Max Algorithm Profit |
| `overall_close_percentage` | Min / Max Overall Score |
| `rap_close_percentage` | Min / Max RAP Score |
| `min_value_of_trade` | Min Trade Value |
| `min_rap_of_trade` | Min Trade RAP |

If one reason is far ahead every time, that setting is too strict for your inventory. If the counts are all small, your items are probably on trade hold or ruled out by [`[Items]`](filtering-items.md).

## The bot won't start after editing the config
The error lists every setting it couldn't read and what it should be, e.g.:
```
These config settings are invalid: [Items] Max Duplicates Owned (must be a whole number)
```
Usually it's `None` or a decimal in a whole-number setting, or a typo.

## All my outbound trades got cancelled after a config change
Set `Keep Trades Sent Before Config Change = True` in [`[Outbounds]`](outbound-settings.md).
