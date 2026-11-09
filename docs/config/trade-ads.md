[← Config guide](README.md)

# [Trade Ads]

Posts a Rolimons trade ad for each account every few minutes, to get more inbound trades. Off unless `Enabled = True`.

## Setup
Set `Enabled = True`. That's it.

With `Auto Rolimons Login = True` (the default) the bot logs each account into Rolimons by itself, using the Roblox cookie you already added. It's the same as pressing "Login with Roblox" on rolimons.com: Roblox shows Rolimons as an authorized app in Settings > Security. The Rolimons cookie it gets is saved in `cookies.json`, so it only logs in once, and again if Rolimons ever logs the account out.

> [!NOTE]
> Rolimons doesn't publish docs for posting ads. The bot uses the same API rolimons.com uses, so if Rolimons changes it, ads stop working and their error message shows in the log. Trading isn't affected.

## Settings
| Setting | What it does |
|---|---|
| `Enabled` | Turns ad posting on. |
| `Auto Rolimons Login` | Logs accounts into Rolimons with their Roblox cookie. With `False`, only accounts that already have a Rolimons cookie in `cookies.json` post ads. Default `True`. |
| `Post Every Minutes` | Minutes between ads for each account. At least `15`, since Rolimons allows one ad every 15 minutes. |
| `Offer Items Using` | Which of your items to list. See below. |
| `Offer Items` | How many items `highest_value`, `lowest_value` and `random` list, `1` to `4`. |
| `Offer Item IDs` | For `manual`: the item IDs to list, separated by commas (1 to 4). |
| `Request Item IDs` | Item IDs you want, separated by commas, or `None`. |
| `Request Tags` | Any of `any`, `demand`, `rares`, `robux`, `upgrade`, `downgrade`, `wishlist`, `projecteds`, `adds`. |

`Request Item IDs` and `Request Tags` can be at most 4 together, and an ad needs at least one of them (except with `outbound`).

## `Offer Items Using` options
| Option | What the ad lists |
|---|---|
| `highest_value` | Your most valuable items |
| `lowest_value` | Your least valuable items |
| `random` | Different items each time |
| `outbound` | One of your open outbound trades: your items, asking for theirs. Each ad uses the next outbound, so they all get a turn. If there are no outbounds yet, it uses `highest_value`. |
| `manual` | The items in `Offer Item IDs`. Any you don't own (or that are on hold or in `Never Give`) are left out. |

With `outbound`, the ad asks for the other person's items instead of `Request Item IDs`, and `Request Tags` only fill the room left (4 total). The outbounds come from the outbound checker, so it needs `Dont Check Outbounds = False`.

The listed items come from the account's tradeable inventory, so items in `Never Give` or on hold are never listed. Bundles can't go in a Rolimons ad.

Nothing is posted while `Dont Send Trades = True` (test mode). If Rolimons refuses an account's cookie, the bot logs in again (at most once an hour). If that fails, the account stops posting until the bot restarts.
