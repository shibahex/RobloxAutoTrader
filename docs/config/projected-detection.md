[← Config guide](README.md)

# [Projected]

A projected item is one whose price is being pushed up on purpose, so its RAP is higher than what it really sells for.

## How the bot decides an item is projected
When the bot looks up an item's sales data (see [How the bot gets sales data](README.md#how-the-bot-gets-sales-data)), it compares today's price with the item's **typical price**: the middle daily price of the last 90 days. If they're too far apart, the item is projected. `Max Price Rise` and `Max Price Drop` set how far is too far.

Example, today's price 10,000 with the default `0.4` / `-0.4`:

| The typical price is | Means | Result |
|---|---|---|
| under 6,000 | the price shot up | projected (Max Price Rise) |
| over 14,000 | the price crashed | projected (Max Price Drop), but only if RAP is also over 14,000 |
| between | normal movement | fine |

A one-day spike or dip doesn't move the typical price, so an item whose price went back to normal isn't projected. An item whose price slowly came down isn't projected either once its RAP has come down with it.

## What happens to projected items
- Items you'd **receive** that are projected are left out, so trades for them aren't made.
- New trades never ask for projected items.
- Trades you already sent are cancelled when an item you'd receive becomes projected, or one you send does. Each can be turned on or off in [`[Outbounds]`](outbound-settings.md).
- Inbound trades that give you a projected item are never accepted.
- Your **own** projected items can still be traded away in new trades.
- **Valued items** are never treated as projected unless `Check Valued Items = True`. Rolimons sets their value, so a jump in their sales price doesn't change what they're worth.

## Settings
| Setting | What it does |
|---|---|
| `Use Rolimons Projected Flag` | `True` also treats items Rolimons marks as projected as projected, on top of the bot's own check. |
| `Check Valued Items` | `True` checks valued items like RAP items. `False` (default) never treats a valued item as projected. |
| `Max Price Rise` | How far **below** today's price the typical price can be. `0.4` = 40%. Default `0.4`. |
| `Max Price Drop` | How far **above** today's price the typical price can be, as a negative number. `-0.4` = 40%. Default `-0.4`. |
| `MinPriceDifference` | **No effect.** Never used, even in older versions. Safe to delete. |

For `Max Price Rise` and `Max Price Drop`: a number between -1 and 1 is a share of today's price, a whole number is Robux (e.g. `1000` = 1,000 Robux below today), and `None` turns that direction off. Setting `Max Price Drop = None` still catches spikes but stops flagging items that crashed.
