# Config Guide

The bot reads its settings from `config.cfg`. Each section of the config has its own page, listed below.

> [!IMPORTANT]
> **`[Trading Settings]` is the section that decides which trades get sent.** Gains, robux, and how many items go on each side all live there. If you want different trades, that's what you change.
>
> Every other section is tweaking: who the bot looks for, how fast it searches, what it does with inbound and outbound trades, and logging. `[Filtering Items]` is the one exception worth knowing about: it can rule items out (like duplicates or slow sellers), so it affects which items show up in trades, but not whether a trade is good enough.

## Sections

**Start here:** [[Trading Settings]](trading-settings.md) decides which trades get sent.

Everything else is tweaking:

| Section | What it's for |
|---|---|
| [[Filtering Generated Trades]](filtering-generated-trades.md) | How long the bot searches, and which trade it picks. |
| [[Filtering Items]](filtering-items.md) | Items the bot won't trade for or give away. |
| [[Inbound Settings]](inbound-settings.md) | Accepting and countering trades sent to you. |
| [[Outbound Settings]](outbound-settings.md) | When to cancel trades you've sent. |
| [[Getting Owners of Items]](getting-owners-of-items.md) | How the bot finds people to trade with. |
| [[Filtering Users]](filtering-users.md) | Skipping people with small inventories. |
| [[Projected Detection]](projected-detection.md) | Avoiding items with faked prices. |
| [[debug]](debug.md) | Test mode and extra logging. |
| [[Discord]](discord.md) | Webhook notifications. |
| [[Trade Ads]](trade-ads.md) | Posting Rolimons trade ads. |
| [[Info]](info.md) | The preset description. |

Something not working? See [Troubleshooting](troubleshooting.md).

---

## Getting a config
`configs/` has ready-made presets. Use **Config Manager > Change Config** to copy one over your `config.cfg`.

| Preset | For |
|---|---|
| `rap_config.cfg` | RAP items only |
| `rap_algorithm.cfg` | RAP items, judged by the RAP Algorithm. Don't use with valued items |
| `small_value.cfg` | Inventories worth about 10–30k, with valued and RAP items |
| `big_value.cfg` | Inventories with lots of valued items (50k+ Value) |
| `rap_to_value.cfg` | Trading RAP items into valued items |
| `value_to_rap.cfg` | Trading valued items for RAP wins |

To give one account its own trading settings, use **Config Manager > Add Account Configs**. An account config only replaces `[Trading Settings]` for that account.

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

That's why the Discord webhook can say **"Value Profit: -500"** on a trade titled **"612 profit"**. Both are right; they measure different things. To allow trades like this, `Minimum Value Gain` must be −500 or lower, or `None`.

## How the bot gets sales data
RAP Algorithm, daily sales, sales gaps and projected checks all come from Roblox's sales history for each item (the price and volume charts on the item's page). The bot looks it up when it loads someone's inventory, and saves it in `projected_checker.json`. An item is looked up again when its saved data is more than 2 days old, or its lowest price has moved 50% or more since. Outbound trades re-check items whose data is more than 6 hours old.

From that history:

| Number | How it's worked out |
|---|---|
| **RAP Algorithm** | The average of the low points (dips) in the item's sale prices. The history is split into thirds, and a third that's far off from the others is ignored first. Because it uses the dips, a few inflated sales don't raise it. |
| **Daily sales** | An estimate of sales per day: the peaks of the sales-volume chart added up and divided by 120 days (80 if a third was ignored). |
| **Sales gap** | The average number of days between days that had sales. |

## Settings that do nothing
Older configs (maybe yours) have settings the bot loads but never uses. They don't change any trades and can be deleted. Two side effects while they're there: an invalid value still stops the bot from starting, and changing one counts as a config change for `Only Cancel Losing Trades After Config Change`.

| Setting | Section |
|---|---|
| `Robux Divide Percentage` | [Trading Settings](trading-settings.md) |
| `Scrape Rolimon Ads` | [Getting Owners of Items](getting-owners-of-items.md) |
| `MinPriceDifference` | [Projected Detection](projected-detection.md) |
| `Enable Mass Sending`, `Always send`, `Always Receive` | `[Mass Sender]`, a section the bot reads but doesn't use |
