[← Config guide](README.md)

# [Getting Owners of Items]

How the bot finds people to trade with: it picks a random item that passes these filters and checks who recently got one.

| Setting | What it does |
|---|---|
| `Minimum Value of Item` | Item's Value must be at least this. |
| `Minimum Rap of Item` | Item's RAP must be at least this. |
| `Minimum Owners of Item` | Item must have at least this many owners. |
| `Minimum Demand of Item` | Item's Rolimons demand must be at least this. |
| `Minimum Trend of Item` | Item's Rolimons trend must be at least this. |
| `Scan Type` | `rap` = only items without a Rolimons value, `value` = only valued items, `both` = either. |
| `Scan Rares` | Only used with `Scan Type = both`: `True` = only rare items, `False` = only non-rare items. |
| `Scrape Rolimon Ads` | **Does nothing.** It's in older configs but the bot never reads Rolimons trade ads. Safe to delete. |

All the minimums are whole numbers. An item without a value, demand or trend passes that check. If nothing matches these filters, the bot says so and waits.
