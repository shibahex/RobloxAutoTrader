# Config Guide

The bot reads its settings from `config.cfg`. This guide goes through every section and what each setting does.

> [!IMPORTANT]
> **`[Trading Settings]` is the section that decides which trades get sent.** Gains, robux, and how many items go on each side all live there. If you want different trades, that's what you change.
>
> Every other section is tweaking: who the bot looks for, how fast it searches, what it does with inbound and outbound trades, and logging. `[Filtering Items]` is the one exception worth knowing about: it can rule items out (like duplicates or slow sellers), so it affects which items show up in trades, but not whether a trade is good enough.

## Contents
- [Basics](#basics)
- [[Trading Settings]](#trading-settings) ← start here
- [[Filtering Generated Trades]](#filtering-generated-trades)
- [[Filtering Items]](#filtering-items)
- [[Inbound Settings]](#inbound-settings)
- [[Outbound Settings]](#outbound-settings)
- [[Getting Owners of Items]](#getting-owners-of-items)
- [[Filtering Users]](#filtering-users)
- [[Projected Detection]](#projected-detection)
- [[debug]](#debug)
- [[Discord]](#discord)
- [[Info]](#info)
- [Troubleshooting](#troubleshooting)

---

## Basics

### Getting a config
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

### Writing values
- `True` / `False` for on/off settings.
- `None` turns a setting off, but **only where this guide says so**.
- Some settings must be a **whole number**. `None` or a decimal there stops the bot from starting.
- Lines starting with `#` are notes and are ignored.

### The 4 numbers
Every trade is judged with these:

| Number | What it is |
|---|---|
| **RAP** | Roblox's recent average price. |
| **Value** | The Rolimons value. Items Rolimons hasn't valued count as **0**. |
| **Overall Value** | The Rolimons value if the item has one, otherwise its RAP. |
| **RAP Algorithm** | The bot's estimate of what an item really sells for, from its sales history. It ignores price spikes, so it's harder to fool than RAP. |

**Gain** = what you receive minus what you give, measured in one of these numbers.

---

## [Trading Settings]

**This is the section that decides your trades.** Every trade the bot comes up with is checked against these settings, and it's only sent if it passes all of them.

### Gains
Each number has a minimum and a maximum gain. They're checked separately, and a trade must pass **all** of them.

| Setting | What it does |
|---|---|
| `Minimum RAP Gain` / `Maximum RAP Gain` | Range for RAP received minus RAP given. |
| `Minimum Overall Value Gain` / `Maximum Overall Value Gain` | Same, for Overall Value. |
| `Minimum Value Gain` / `Maximum Value Gain` | Same, for Value. |
| `Minimum Rap Algorithm Gain` / `Maximum Rap Algorithm Gain` | Same, for the RAP Algorithm. |

- **Minimum** is the least you'll accept. It can be negative if you're fine taking a small loss in one number to win in another (e.g. lose RAP to gain Value).
- **Maximum** stops offers so lopsided that nobody accepts them.
- `None` = no limit.
- A number between **-1 and 1** is a percentage of your side: `0.1` means "at least 10% of what I'm giving".

> [!WARNING]
> Because the gains are checked separately, RAP items have **0 Value**. A trade can be +3000 RAP and still have a Value gain of 0. So `Minimum Value Gain = 1` means only trades that include valued items can be sent.

### RAP Algorithm for valued items
`RAP Algorithm for Valued Items` sets which RAP Algorithm number a **valued** item counts as:

| Option | Valued items count as |
|---|---|
| `rap_algo` | The bot's sales estimate, same as RAP items |
| `rolimon_value` | Their Rolimons value |
| `zero_value` | 0, so valued items don't affect RAP Algorithm gain at all |

### Robux
| Setting | What it does |
|---|---|
| `Trade Robux` | `True` adds Robux to your side when you'd receive more RAP than you give. |
| `Max Robux` | The most Robux it adds to one trade. |

The amount is (their RAP − your RAP) ÷ 4, capped at half your side's RAP and at `Max Robux`.

### Score percentages
Score measures how uneven a trade is, as a percent of the whole trade:

```
(what you get − what you give) ÷ (both sides added together) × 100
```

`0` is perfectly even, `10` means you get a bit more, and a negative number means you get less.

| Setting | What it does |
|---|---|
| `Min Overall Value Score Percentage` / `Max Overall Value Score Percentage` | How uneven a trade can be, by Overall Value. |
| `Min RAP Score Percentage` / `Max RAP Score Percentage` | Same, by RAP. |

`None` = no limit. These are a second way to stop greedy offers, relative to the size of the trade instead of a fixed number.

### Items per side
| Setting | What it does |
|---|---|
| `Minimum Items on Your Side` / `Maximum Items on Your Side` | How many of your items a trade can have. |
| `Minimum Items on Their Side` / `Maximum Items on Their Side` | How many of their items a trade can have. |

Whole numbers only. 1-for-1 trades are never sent. Higher maximums mean far more combinations to check, so each search is slower (see `Max Seconds Spent on Generating Trades`).

### Trade size
| Setting | What it does |
|---|---|
| `Minimum Value Sum Of Trade` | Both sides' Value added together must be at least this. Above 0 means the trade must include valued items. |
| `Minimum Rap Sum Of Trade` | Both sides' RAP added together must be at least this. |

`0` = no limit.

### Faces and gears
| Setting | What it does |
|---|---|
| `Trade For Faces` | `True` allows **receiving** faces. |
| `Trade For Gears` | `True` allows **receiving** gears. |

Your own faces and gears can always be traded away.

---

## [Filtering Generated Trades]
How long the bot searches, and which trade it picks when several pass.

| Setting | What it does |
|---|---|
| `Max Seconds Spent on One User` | If an account hasn't sent a trade in this many seconds, move on to your next account. |
| `Max Seconds Spent on Generating Trades` | Time limit for finding a trade with one person. When time's up, it picks from what it found, or moves on if it found nothing. |
| `Max Valid Trades` | Stop searching once more than this many trades pass, then pick one. `None` = keep searching until the time limit. Lower is faster. |
| `Select Trade Using` | Which passing trade gets sent. See below. |

### How the search works
It goes through your items one at a time, then in pairs, then threes, and so on, and tries each against every combination of theirs. With big inventories it can run out of time before reaching the bigger combinations. Raising the time limit checks more; setting `Max Valid Trades` makes it stop as soon as it has enough to choose from.

### `Select Trade Using` options
"Gain" means what you get minus what you give.

| Option | Picks the trade with |
|---|---|
| `lowest_rap_gain` / `highest_rap_gain` | Smallest / biggest RAP gain |
| `lowest_value_gain` / `highest_value_gain` | Smallest / biggest Value gain |
| `lowest_overall_gain` / `highest_overall_gain` | Smallest / biggest Overall Value gain |
| `lowest_algo_gain` / `highest_algo_gain` | Smallest / biggest RAP Algorithm gain |
| `closest_score_based_on_overall_value` | The most even trade by Overall Value |
| `closest_score_based_on_rap` | The most even trade by RAP |
| `lowest_sum_of_trade_value` / `highest_sum_of_trade_value` | Smallest / biggest trade by total Value |
| `lowest_sum_of_trade_rap` / `highest_sum_of_trade_rap` | Smallest / biggest trade by total RAP |
| `lowest_sum_of_overall_value` / `highest_sum_of_overall_value` | Smallest / biggest trade by total Overall Value |
| `lowest_demand` / `highest_demand` | Lowest / highest Rolimons demand of all items added up |
| `lowest_volume_gain` / `highest_volume_gain` | Daily sales you get minus daily sales you give |
| `lowest_sum_of_volume` / `highest_sum_of_volume` | Daily sales of all items added up |
| `upgrade` | You give more items than you get |
| `downgrade` | You get more items than you give |
| `random` | Any of them |

The "lowest gain" options send trades that are still wins but closer to fair, which people accept more often. The "highest gain" options win more per trade but get declined more. An invalid option falls back to `lowest_rap_gain` with a warning.

---

## [Filtering Items]
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
- The two sales settings only apply to RAP items (items without a Rolimons value). RAP items the bot has no sales history for are skipped.

---

## [Inbound Settings]
What to do with trades people send you. Checked every `Check Inbounds Every Minutes`.

| Setting | What it does |
|---|---|
| `Accept Valid Trades` | Accepts trades that pass your config. Off by default. |
| `Counter Trades` | Counters trades that aren't accepted, using a trade made from your config. |
| `Dont Counter Wins` | Leaves trades that are already a win in Overall Value alone instead of countering. |
| `Check Inbounds Every Minutes` | Minutes between checks. Missing, 0 or negative falls back to 30. |

### What gets accepted
A trade is accepted only if it:
- passes your **minimum** gains in `[Trading Settings]`. Maximums and score % are ignored, because a bigger win is still a win.
- passes your `[Filtering Items]` rules for the items you'd receive.
- doesn't ask for your Robux.
- doesn't give you projected items.

Before accepting, it re-checks the prices of anything it hasn't looked at in the last 6 hours.

> [!CAUTION]
> Accepting can't be undone. Only turn on `Accept Valid Trades` once your minimum gains are where you want them. Loose minimums (like `Minimum Value Gain = 1`) will accept near-even trades.

---

## [Outbound Settings]
When to cancel trades you've sent. They're checked every 30 minutes, and re-priced every ~2 minutes when Rolimons updates (without extra Roblox requests).

An outbound trade is cancelled when:
- it no longer passes your minimum gains, loosened by the offsets below;
- you'd receive a projected item;
- you'd end up with more duplicates than `Maximum Amount of Duplicate Items`.

Maximums and score % aren't checked.

| Setting | What it does |
|---|---|
| `Outbound Minimum Gain Offset to Cancel` | Taken off `Minimum RAP Gain` and `Minimum Overall Value Gain`. Whole number. |
| `RAP Algorithm Gain Offset to Cancel` | Taken off `Minimum Rap Algorithm Gain`. Whole number. |
| `Only Cancel Losing Trades After Config Change` | `True` = after you change your config, trades sent before the change are only cancelled if they become a loss (or give you a projected item). |

**Offset example:** `Minimum RAP Gain = 600` and an offset of `200` means a trade is cancelled once its RAP gain drops under 400. The result never goes below 0 (unless your minimum is negative), so trades that turn into a loss always get cancelled.

Without `Only Cancel Losing Trades After Config Change`, making your config stricter cancels every outbound that doesn't meet the new settings.

---

## [Getting Owners of Items]
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

All the minimums are whole numbers. An item without a value, demand or trend passes that check. If nothing matches these filters, the bot says so and waits.

---

## [Filtering Users]
| Setting | What it does |
|---|---|
| `Minimum Total Items` | Skips people with fewer tradeable items than this, after your `[Filtering Items]` rules. Whole number. |

---

## [Projected Detection]
A projected item is one whose price is being pushed up on purpose. The bot never receives projected items.

The bot checks each item's sales history itself: an item counts as projected if its price swung more than 40% in the last 90 days.

| Setting | What it does |
|---|---|
| `Detect Rolimons Projecteds` | `True` also treats items Rolimons marks as projected as projected. |

---

## [debug]
| Setting | What it does |
|---|---|
| `Dont Send Trades` | Test mode: finds trades but doesn't send, accept or counter anything. |
| `Dont Check Outbounds` | Turns off the outbound checker. |
| `Ignore trade limit` | Keeps going when Roblox says the account hit its daily trade limit. |
| `Show Trade Debug` | Prints details while making trades. |
| `Show Scanning Users` | Prints the users being scanned. |
| `Show Scanning Inventory` | Prints why items in an inventory get skipped. |

### Testing a config
```
Dont Send Trades = True
Dont Check Outbounds = True
```
Turn on both. Without `Dont Check Outbounds`, your real outbound trades get checked against the test config, and can be cancelled.

---

## [Discord]
Webhook URLs. Leave one empty to turn it off.

| Setting | Posts when |
|---|---|
| `Send Webhook` | A trade is sent |
| `Completed Webhook` | A trade completes |
| `Error Webhook` | The bot hits an error, or an account stops working (for example, an expired cookie) |

---

## [Info]
| Setting | What it does |
|---|---|
| `Description` | Shown next to the preset in **Config Manager > Change Config**. |

---

## Troubleshooting

### "Couldnt find valid_trades heres invalid trades reasons"
The bot checked every trade with that person and none passed `[Trading Settings]`. The counts show which setting blocked them most:

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

If one reason is far ahead every time, that setting is too strict for your inventory. If the counts are all small, your items are probably on trade hold or ruled out by `[Filtering Items]`.

### The bot won't start after editing the config
The error lists every setting it couldn't read and what it should be, e.g.:
```
These config settings are invalid: [Filtering Items] Maximum Amount of Duplicate Items (must be a whole number)
```
Usually it's `None` or a decimal in a whole-number setting, or a typo.

### All my outbound trades got cancelled after a config change
Set `Only Cancel Losing Trades After Config Change = True` in `[Outbound Settings]`.
