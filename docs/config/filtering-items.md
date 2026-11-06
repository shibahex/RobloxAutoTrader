[← Config guide](README.md)

# [Filtering Items]

Which items the bot is willing to trade for or trade away. These can rule items out before trades are made.

| Setting | What it does |
|---|---|
| `NFT` | Not for trade: items you never give away. |
| `NFR` | Not for receive: items you never take. |
| `Maximum Amount of Duplicate Items` | Extra copies of one item you can end up owning. `0` = never trade for something you already own, `1` = own up to 2. Whole number. |
| `Maximum Amount of Trader Duplicate Items` | Extra copies of the same item you'll take from one person. `0` = at most 1 of each. Whole number. |
| `Minimum Valued Item Demand` | Valued items you'd receive need at least this Rolimons demand: `0` Terrible, `1` Low, `2` Normal, `3` High, `4` Amazing. Whole number. |
| `Minimum Daily Sales of Item` | RAP items you'd receive must sell at least this many times a day on average. `None` = no limit. |
| `Maximum Average Gaps in Sales` | RAP items you'd receive must sell at least every this many days on average. `None` = no limit. |

- `NFT` / `NFR` take item IDs separated by commas, e.g. `1029025, 1191135761`. `None` = empty. Bundles need `2:` in front, e.g. `2:939596`.
- The two sales settings only apply to RAP items (items without a Rolimons value).
- Any item you'd receive that the bot has no sales data for is skipped, valued or not. It looks the data up when it loads someone's inventory (see [How the bot gets sales data](README.md#how-the-bot-gets-sales-data)), so this only happens when Roblox's sales API fails for that item.
