[← Config guide](README.md)

# [Items]

Which items the bot is willing to trade for or trade away. These can rule items out before trades are made.

| Setting | What it does |
|---|---|
| `Never Give` | Not for trade: items you never give away. |
| `Never Receive` | Not for receive: items you never take. |
| `Max Duplicates Owned` | Extra copies of one item you can end up owning. `0` = never trade for something you already own, `1` = own up to 2. Whole number. |
| `Max Duplicates From Trader` | Extra copies of the same item you'll take from one person. `0` = at most 1 of each. Whole number. |
| `Min Demand` | Valued items you'd receive need at least this Rolimons demand: `0` Terrible, `1` Low, `2` Normal, `3` High, `4` Amazing. Whole number. |
| `Min Daily Sales` | RAP items you'd receive must sell at least this many times a day on average. `None` = no limit. |
| `Max Days Between Sales` | RAP items you'd receive must sell at least every this many days on average. `None` = no limit. |
| `Sales History Days` | How many days of sales history the RAP Algorithm, daily sales and days between sales use. Default `90`. Longer = old prices count too, so an item that used to sell higher gets a RAP Algorithm well above what it sells for now. Whole number. |

- `Never Give` / `Never Receive` take item IDs separated by commas, e.g. `1029025, 1191135761`. `None` = empty. Bundles work the same way, just their ID.
- The two sales settings only apply to RAP items (items without a Rolimons value).
- Any item you'd receive that the bot has no sales data for is skipped, valued or not. It looks the data up when it loads someone's inventory (see [How the bot gets sales data](README.md#how-the-bot-gets-sales-data)), so this only happens when Roblox's sales API fails for that item.
