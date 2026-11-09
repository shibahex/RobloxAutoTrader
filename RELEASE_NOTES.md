## What's new

### Faster trade searching
- The bot only builds trades that can land inside your profit range. Trades that would go over your maximum or can't reach your minimum are skipped before they're built, so it checks far fewer trades for the same result.
- The other person's side of the trade is worked out once and reused instead of rebuilt for every one of your items.
- Your profit limits are worked out once per search, and each trade stops being checked at the first rule it fails.
- Picking which trade to send uses less memory: it keeps only the best trades instead of every one that passed, and still picks the same trade.

### Inbounds: biggest win first
- The bot checks all your inbounds first, then accepts the passing ones from the biggest Overall win down.
- A trade that asks for items you just gave away is skipped, and items you just received count toward `Max Duplicates Owned` for the next one.

### Automatic Rolimons login for trade ads
- `[Trade Ads]` `Auto Rolimons Login = True` (default) logs each account into Rolimons with its Roblox cookie. No more pasting Rolimons cookies.
- If Rolimons rejects a cookie, the bot logs in again (at most once an hour).
- The Rolimons Cookies menu in the account manager is gone.

### Easier config
- Shorter setting and section names: `[Profit]`, `[Trade Rules]`, `[Picking Trades]`, `[Items]`, `[Finding Traders]`, `[Projected]`, `[Inbounds]`, `[Outbounds]`. **Old configs still work.** The old names are listed in [`docs/config/README.md`](docs/config/README.md#old-setting-names).
- **Config Manager > Edit config.cfg** changes settings without opening the file. It shows each setting's notes and lists the valid choices. Comments are kept, and a change that would break the config isn't saved.
- Account configs can now hold any of `[Profit]`, `[Trade Rules]`, `[Items]`, `[Picking Trades]` and the `[Outbounds]` offsets, and only the settings you change.
- `Pick Trade By` can combine options: `a + b` breaks ties in order, and `blend: a, b, c` weighs them all.
- The inbound `Max Overall Profit` default is now 1500.

### Finding traders
- Owners are read page by page, and each scan carries on where the last one stopped. Progress is saved in `owner_scan_cache.json` and shared by all accounts (`Owner Pages Per Scan`, `Recent Owner Days`, `Remember Scanned Owners Days`).

### Other changes
- `[Items]` `Sales History Days` (default 90) sets how much sales history the RAP Algorithm and the sales filters use.
- Projected detection compares today's price with the 90-day typical price, so one-day spikes no longer flag an item. New `Check Valued Items`, `Cancel If Receiving Projected` and `Cancel If Sending Projected` settings.
