[← Config guide](README.md)

# [Trading Settings]

**This is the section that decides your trades.** Every trade the bot comes up with is checked against these settings, and it's only sent if it passes all of them.

Trades are judged with 4 numbers: RAP, Value, Overall Value and RAP Algorithm. If those aren't familiar, read [The 4 numbers](README.md#the-4-numbers) first.

## Gains
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
>
> A trade can also lose Value and still be a win in Overall Value. See [Value vs Overall Value](README.md#value-vs-overall-value) for a real example (−500 Value, +612 Overall).

## RAP Algorithm for valued items
`RAP Algorithm for Valued Items` sets which RAP Algorithm number a **valued** item counts as:

| Option | Valued items count as |
|---|---|
| `rap_algo` | The bot's sales estimate, same as RAP items |
| `rolimon_value` | Their Rolimons value |
| `zero_value` | 0, so valued items don't affect RAP Algorithm gain at all |

## Robux
| Setting | What it does |
|---|---|
| `Trade Robux` | `True` adds Robux to your side when you'd receive more RAP than you give. |
| `Max Robux` | The most Robux it adds to one trade. |

The amount is (their RAP − your RAP) ÷ 4, capped at half your side's RAP and at `Max Robux`.

The Robux counts as part of your side in the RAP, Overall Value and RAP Algorithm gains and the score percentages, so a trade still has to pass your minimums after paying it. Value gain doesn't include it, since Value only counts Rolimons values. Robux the other person adds (on inbounds) counts for you the same way.

| Setting | What it does |
|---|---|
| `Robux Divide Percentage` | **Does nothing.** It's in older configs, but the bot always divides by 4. Safe to delete. |

## Score percentages
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

## Items per side
| Setting | What it does |
|---|---|
| `Minimum Items on Your Side` / `Maximum Items on Your Side` | How many of your items a trade can have. |
| `Minimum Items on Their Side` / `Maximum Items on Their Side` | How many of their items a trade can have. |

Whole numbers only. 1-for-1 trades are never sent. Higher maximums mean far more combinations to check, so each search is slower (see [`Max Seconds Spent on Generating Trades`](filtering-generated-trades.md)).

## Trade size
| Setting | What it does |
|---|---|
| `Minimum Value Sum Of Trade` | Both sides' Value added together must be at least this. Above 0 means the trade must include valued items. |
| `Minimum Rap Sum Of Trade` | Both sides' RAP added together must be at least this. |

`0` = no limit.

## Faces and gears
| Setting | What it does |
|---|---|
| `Trade For Faces` | `True` allows **receiving** faces. |
| `Trade For Gears` | `True` allows **receiving** gears. |

Your own faces and gears can always be traded away.
