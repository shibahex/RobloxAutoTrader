[← Config guide](README.md)

# [Finding Traders]

How the bot finds people to trade with: it picks a random item that passes these filters and checks who recently got one.

| Setting | What it does |
|---|---|
| `Min Item Value` | Item's Value must be at least this. |
| `Min Item RAP` | Item's RAP must be at least this. |
| `Min Item Owners` | Item must have at least this many owners. |
| `Min Item Demand` | Item's Rolimons demand must be at least this. |
| `Min Item Trend` | Item's Rolimons trend must be at least this. |
| `Scan Type` | `rap` = only items without a Rolimons value, `value` = only valued items, `both` = either. |
| `Scan Rares` | Only used with `Scan Type = both`: `True` = only rare items, `False` = only non-rare items. |
| `Owner Pages Per Scan` | Owners are read a page (100 owners) at a time: each time an item is picked, the bot reads its next this-many pages, carrying on where the last scan of that item stopped, and tries every owner on them who got it recently. Once every page has been read, the item is skipped. Bundles: Roblox doesn't list their owners, so the bot reads the people reselling them instead. Default `2`. |
| `Recent Owner Days` | Only owners who got the item in the last this many days count (they're likely still trading). Default `7`. |
| `Remember Scanned Owners Days` | How long the bot remembers where it stopped on each item (saved in `owner_scan_cache.json`, shared by all accounts). An item whose owners were all read is skipped until then. After this many days it starts from its first page again. `0` = don't remember. Default `3`. |
| `Scrape Rolimon Ads` | **Does nothing.** It's in older configs but the bot never reads Rolimons trade ads. Safe to delete. |

All the minimums are whole numbers. An item without a value, demand or trend passes that check. If nothing matches these filters, the bot says so and waits.
| `Min Trader Items` | Skips people with fewer tradeable items than this, after your [`[Items]`](filtering-items.md) rules. Whole number. |
