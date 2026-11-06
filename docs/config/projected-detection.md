[← Config guide](README.md)

# [Projected Detection]

A projected item is one whose price is being pushed up on purpose, so its RAP is higher than what it really sells for.

## How the bot decides an item is projected
When the bot looks up an item's sales data (see [How the bot gets sales data](README.md#how-the-bot-gets-sales-data)), it compares the price on every day of the last 90 days with today's price. If any day is too far off, the item is projected. `Maximum Graph Difference` and `Minimum Graph Difference` set how far is too far.

Example, today's price 10,000 with the default `0.4` / `-0.4`:

| A past day was | Means | Result |
|---|---|---|
| under 6,000 | the price shot up since | projected (Maximum Graph Difference) |
| over 14,000 | the price crashed since | projected (Minimum Graph Difference) |
| between | normal movement | fine |

One unusual day in the last 90 days is enough to mark an item.

## What happens to projected items
- Items you'd **receive** that are projected are left out, so trades for them aren't made.
- Outbound trades where you'd receive a projected item are cancelled.
- Inbound trades that give you a projected item are never accepted.
- Your **own** projected items can still be traded away.

## Settings
| Setting | What it does |
|---|---|
| `Detect Rolimons Projecteds` | `True` also treats items Rolimons marks as projected as projected, on top of the bot's own check. |
| `Maximum Graph Difference` | How far **below** today's price a past day can be. `0.4` = 40%. Default `0.4`. |
| `Minimum Graph Difference` | How far **above** today's price a past day can be, as a negative number. `-0.4` = 40%. Default `-0.4`. |
| `MinPriceDifference` | **No effect.** Never used, even in older versions. Safe to delete. |

For both Graph Difference settings: a number between -1 and 1 is a share of today's price, a whole number is Robux (e.g. `1000` = 1,000 Robux below today), and `None` turns that direction off. Setting `Minimum Graph Difference = None` still catches spikes but stops flagging items that crashed.
