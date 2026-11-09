# Config Guide

The bot reads its settings from `config.cfg`. Each section of the config has its own page, listed below.

> [!IMPORTANT]
> **`[Profit]` and `[Trade Rules]` decide which trades get sent.** Profit, robux, and how many items go on each side all live there. If you want different trades, that's what you change.
>
> Every other section is tweaking: who the bot looks for, how fast it searches, what it does with inbound and outbound trades, and logging. `[Items]` is the one exception worth knowing about: it can rule items out (like duplicates or slow sellers), so it affects which items show up in trades, but not whether a trade is good enough.

## Sections

**Start here:** [`[Profit]` and `[Trade Rules]`](trading-settings.md) decide which trades get sent.

Everything else is tweaking:

| Section | What it's for |
|---|---|
| [[Picking Trades]](filtering-generated-trades.md) | How long the bot searches, and which trade it picks. |
| [[Items]](filtering-items.md) | Items the bot won't trade for or give away. |
| [[Finding Traders]](getting-owners-of-items.md) | How the bot finds people to trade with, and who it skips. |
| [[Projected]](projected-detection.md) | Avoiding items with faked prices. |
| [[Inbounds]](inbound-settings.md) | Accepting and countering trades sent to you. |
| [[Outbounds]](outbound-settings.md) | When to cancel trades you've sent. |
| [[Trade Ads]](trade-ads.md) | Posting Rolimons trade ads. |
| [[Discord]](discord.md) | Webhook notifications. |
| [[Debug]](debug.md) | Test mode and extra logging. |
| [[Info]](info.md) | The preset description. |

Something not working? See [Troubleshooting](troubleshooting.md).

---

## Getting a config
`configs/` has ready-made presets. Use **Config Manager > Use a preset for config.cfg** to copy one over your `config.cfg`.

| Preset | For |
|---|---|
| `rap_config.cfg` | RAP items only |
| `rap_algorithm.cfg` | RAP items, judged by the RAP Algorithm. Don't use with valued items |
| `small_value.cfg` | Inventories worth about 10–30k, with valued and RAP items |
| `big_value.cfg` | Inventories with lots of valued items (50k+ Value) |
| `rap_to_value.cfg` | Trading RAP items into valued items |
| `value_to_rap.cfg` | Trading valued items for RAP wins |

To change `config.cfg` without opening the file, use **Config Manager > Edit config.cfg**: pick a section and a setting, and it shows the setting's notes and the easiest way to change it (a numbered list for settings with a few options, True/False, add/remove for item lists like `Never Give` by ID or name, on/off for tags, and a builder for `Pick Trade By`). Comments are kept, the old file is saved as `config.backup.cfg`, and a change that would stop the config from loading isn't saved.

To give one account its own settings, use **Config Manager > Account configs**, pick the account, then a section (`[Profit]`, `[Trade Rules]`, `[Items]`, `[Picking Trades]`, `[Outbounds]` offsets). An account config only holds the settings you change there; everything else comes from `config.cfg`.

## Writing values
- `True` / `False` for on/off settings.
- `None` turns a setting off, but **only where this guide says so**.
- Some settings must be a **whole number**. `None` or a decimal there stops the bot from starting.
- Lines starting with `#` are notes and are ignored.

## The 4 numbers
Every trade is judged with these:

| Number | What it is |
|---|---|
| **RAP** | Roblox's recent average price. |
| **Value** | The Rolimons value. Items Rolimons hasn't valued count as **0**. |
| **Overall Value** | The Rolimons value if the item has one, otherwise its RAP. |
| **RAP Algorithm** | The bot's estimate of what an item really sells for, from its sales history. It ignores price spikes, so it's harder to fool than RAP. |

**Gain** = what you receive minus what you give, measured in one of these numbers.

## Value vs Overall Value
- **Value** only counts items Rolimons has valued. RAP items count as **0**.
- **Overall Value** counts every item: its value, or its RAP if it has none.

So one trade can lose Value and still be a win. A real trade the bot made:

| | You give | You get | Gain |
|---|---:|---:|---:|
| Valued items | 4000 | 3500 | |
| RAP items | 2903 | 4015 | |
| **Value** (valued items only) | 4000 | 3500 | **−500** |
| **Overall Value** (everything) | 6903 | 7515 | **+612** |

The items: you gave Traffic Cone (valued), Entombed Miner's Headlamp and Specter Time Fedora, and got Bighead (valued), Guardian Angel Wings and Sinister Branches.

That's why the Discord webhook can say **"Value Profit: -500"** on a trade titled **"612 profit"**. Both are right; they measure different things. To allow trades like this, `Min Value Profit` must be −500 or lower, or `None`.

## How the bot gets sales data
RAP Algorithm, daily sales, sales gaps and projected checks all come from Roblox's sales history for each item (the price and volume charts on the item's page). The bot looks it up when it loads someone's inventory, and saves it in `projected_checker.json`. An item is looked up again when its saved data is more than 2 days old, or its lowest price has moved 50% or more since. Outbound trades re-check items whose data is more than 6 hours old.

From the last 90 days of that history (`[Items]` `Sales History Days`; the whole history if those days have too few sales):

| Number | How it's worked out |
|---|---|
| **RAP Algorithm** | The average of the low points (dips) in the item's sale prices. The history is split into thirds, and a third that's far off from the others is ignored first. Because it uses the dips, a few inflated sales don't raise it. |
| **Daily sales** | An estimate of sales per day: the peaks of the sales-volume chart added up and divided by 120 days (80 if a third was ignored). |
| **Sales gap** | The average number of days between days that had sales. |

## Settings that do nothing
Older configs (maybe yours) have settings the bot loads but never uses. They don't change any trades and can be deleted. Two side effects while they're there: an invalid value still stops the bot from starting, and changing one counts as a config change for `Keep Trades On Config Change`.

| Setting | Section |
|---|---|
| `Robux Divide Percentage` | [Trade Rules](trading-settings.md) |
| `Scrape Rolimon Ads` | [Finding Traders](getting-owners-of-items.md) |
| `MinPriceDifference` | [Projected](projected-detection.md) |
| `Enable Mass Sending`, `Always send`, `Always Receive` | `[Mass Sender]`, a section the bot reads but doesn't use |

## Old setting names
Older configs use older names. They still work, so you don't have to change anything. If a file has both, the new name wins.

| Old | New |
|---|---|
| `[Trading Settings]` `Minimum Overall Value Gain` | `[Profit]` `Min Overall Profit` |
| `[Trading Settings]` `Maximum Overall Value Gain` | `[Profit]` `Max Overall Profit` |
| `[Trading Settings]` `Minimum Value Gain` | `[Profit]` `Min Value Profit` |
| `[Trading Settings]` `Maximum Value Gain` | `[Profit]` `Max Value Profit` |
| `[Trading Settings]` `Minimum RAP Gain` | `[Profit]` `Min RAP Profit` |
| `[Trading Settings]` `Maximum RAP Gain` | `[Profit]` `Max RAP Profit` |
| `[Trading Settings]` `Minimum Rap Algorithm Gain` | `[Profit]` `Min Algorithm Profit` |
| `[Trading Settings]` `Maximum Rap Algorithm Gain` | `[Profit]` `Max Algorithm Profit` |
| `[Trading Settings]` `Skip Value Gain When No Valued Items` | `[Profit]` `Skip Value Profit If No Valued Items` |
| `[Trading Settings]` `RAP Algorithm for Valued Items` | `[Profit]` `Algorithm For Valued Items` |
| `[Trading Settings]` `Minimum Items on Your Side` | `[Trade Rules]` `Min Items Yours` |
| `[Trading Settings]` `Maximum Items on Your Side` | `[Trade Rules]` `Max Items Yours` |
| `[Trading Settings]` `Minimum Items on Their Side` | `[Trade Rules]` `Min Items Theirs` |
| `[Trading Settings]` `Maximum Items on Their Side` | `[Trade Rules]` `Max Items Theirs` |
| `[Trading Settings]` `Trade Robux` | `[Trade Rules]` `Add Robux` |
| `[Trading Settings]` `Max Robux` | `[Trade Rules]` `Max Robux` |
| `[Trading Settings]` `Robux Divide Percentage` | `[Trade Rules]` `Robux Divide Percentage` |
| `[Trading Settings]` `Min Overall Value Score Percentage` | `[Trade Rules]` `Min Overall Score` |
| `[Trading Settings]` `Max Overall Value Score Percentage` | `[Trade Rules]` `Max Overall Score` |
| `[Trading Settings]` `Min RAP Score Percentage` | `[Trade Rules]` `Min RAP Score` |
| `[Trading Settings]` `Max RAP Score Percentage` | `[Trade Rules]` `Max RAP Score` |
| `[Trading Settings]` `Minimum Value Sum Of Trade` | `[Trade Rules]` `Min Trade Value` |
| `[Trading Settings]` `Minimum Rap Sum Of Trade` | `[Trade Rules]` `Min Trade RAP` |
| `[Trading Settings]` `Trade For Faces` | `[Trade Rules]` `Receive Faces` |
| `[Trading Settings]` `Trade For Gears` | `[Trade Rules]` `Receive Gears` |
| `[Filtering Generated Trades]` `Max Seconds Spent on One User` | `[Picking Trades]` `Max Seconds Per Account` |
| `[Filtering Generated Trades]` `Max Seconds Spent on Generating Trades` | `[Picking Trades]` `Max Seconds Per Trader` |
| `[Filtering Generated Trades]` `Max Valid Trades` | `[Picking Trades]` `Stop After Passing Trades` |
| `[Filtering Generated Trades]` `Select Trade Using` | `[Picking Trades]` `Pick Trade By` |
| `[Filtering Generated Trades]` `Outbound Variety` | `[Picking Trades]` `Outbound Variety` |
| `[Filtering Items]` `NFT` | `[Items]` `Never Give` |
| `[Filtering Items]` `NFR` | `[Items]` `Never Receive` |
| `[Filtering Items]` `Maximum Amount of Duplicate Items` | `[Items]` `Max Duplicates Owned` |
| `[Filtering Items]` `Maximum Amount of Trader Duplicate Items` | `[Items]` `Max Duplicates From Trader` |
| `[Filtering Items]` `Minimum Valued Item Demand` | `[Items]` `Min Demand` |
| `[Filtering Items]` `Minimum Daily Sales of Item` | `[Items]` `Min Daily Sales` |
| `[Filtering Items]` `Maximum Average Gaps in Sales` | `[Items]` `Max Days Between Sales` |
| `[Getting Owners of Items]` `Minimum Value of Item` | `[Finding Traders]` `Min Item Value` |
| `[Getting Owners of Items]` `Minimum Rap of Item` | `[Finding Traders]` `Min Item RAP` |
| `[Getting Owners of Items]` `Minimum Owners of Item` | `[Finding Traders]` `Min Item Owners` |
| `[Getting Owners of Items]` `Minimum Demand of Item` | `[Finding Traders]` `Min Item Demand` |
| `[Getting Owners of Items]` `Minimum Trend of Item` | `[Finding Traders]` `Min Item Trend` |
| `[Getting Owners of Items]` `Scan Type` | `[Finding Traders]` `Scan Type` |
| `[Getting Owners of Items]` `Scan Rares` | `[Finding Traders]` `Scan Rares` |
| `[Getting Owners of Items]` `Scrape Rolimon Ads` | `[Finding Traders]` `Scrape Rolimon Ads` |
| `[Getting Owners of Items]` `Owner Pages Per Scan` | `[Finding Traders]` `Owner Pages Per Scan` |
| `[Getting Owners of Items]` `Recent Owner Days` | `[Finding Traders]` `Recent Owner Days` |
| `[Getting Owners of Items]` `Remember Scanned Owners Days` | `[Finding Traders]` `Remember Scanned Owners Days` |
| `[Filtering Users]` `Minimum Total Items` | `[Finding Traders]` `Min Trader Items` |
| `[Projected Detection]` `Detect Rolimons Projecteds` | `[Projected]` `Use Rolimons Projected Flag` |
| `[Projected Detection]` `Maximum Graph Difference` | `[Projected]` `Max Price Rise` |
| `[Projected Detection]` `Minimum Graph Difference` | `[Projected]` `Max Price Drop` |
| `[Inbound Settings]` `Minimum Overall Value Gain` | `[Inbounds]` `Min Overall Profit` |
| `[Inbound Settings]` `Maximum Overall Value Gain` | `[Inbounds]` `Max Overall Profit` |
| `[Inbound Settings]` `Minimum Value Gain` | `[Inbounds]` `Min Value Profit` |
| `[Inbound Settings]` `Maximum Value Gain` | `[Inbounds]` `Max Value Profit` |
| `[Inbound Settings]` `Minimum RAP Gain` | `[Inbounds]` `Min RAP Profit` |
| `[Inbound Settings]` `Maximum RAP Gain` | `[Inbounds]` `Max RAP Profit` |
| `[Inbound Settings]` `Minimum Rap Algorithm Gain` | `[Inbounds]` `Min Algorithm Profit` |
| `[Inbound Settings]` `Maximum Rap Algorithm Gain` | `[Inbounds]` `Max Algorithm Profit` |
| `[Inbound Settings]` `Accept Valid Trades` | `[Inbounds]` `Accept Good Trades` |
| `[Inbound Settings]` `Counter Trades` | `[Inbounds]` `Counter` |
| `[Inbound Settings]` `Dont Counter Wins` | `[Inbounds]` `Skip Countering Wins` |
| `[Inbound Settings]` `Decline If No Counter` | `[Inbounds]` `Decline If No Counter` |
| `[Inbound Settings]` `Maximum Amount of Duplicate Items` | `[Inbounds]` `Max Duplicates Owned` |
| `[Inbound Settings]` `Maximum Amount of Trader Duplicate Items` | `[Inbounds]` `Max Duplicates From Trader` |
| `[Inbound Settings]` `Max Counters Per Trader` | `[Inbounds]` `Max Counters Per Trader` |
| `[Inbound Settings]` `Instant Reply Minutes` | `[Inbounds]` `Bot Reply Minutes` |
| `[Inbound Settings]` `Instant Replies To Call It A Bot` | `[Inbounds]` `Bot Replies` |
| `[Inbound Settings]` `Counter Memory Hours` | `[Inbounds]` `Counter Memory Hours` |
| `[Inbound Settings]` `Check Inbounds Every Minutes` | `[Inbounds]` `Check Every Minutes` |
| `[Outbound Settings]` `Outbound Minimum Gain Offset to Cancel` | `[Outbounds]` `Overall And RAP Cancel Offset` |
| `[Outbound Settings]` `RAP Algorithm Gain Offset to Cancel` | `[Outbounds]` `Algorithm Cancel Offset` |
| `[Outbound Settings]` `Keep Trades Sent Before Config Change` | `[Outbounds]` `Keep Trades On Config Change` |
| `[Outbound Settings]` `Cancel If Receiving Item Becomes Projected` | `[Outbounds]` `Cancel If Receiving Projected` |
| `[Outbound Settings]` `Cancel If Sending Item Becomes Projected` | `[Outbounds]` `Cancel If Sending Projected` |
