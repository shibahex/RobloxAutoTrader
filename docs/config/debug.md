[← Config guide](README.md)

# [Debug]

| Setting | What it does |
|---|---|
| `Dont Send Trades` | Test mode: finds trades but doesn't send, accept or counter anything. Trades it would have sent are still printed and posted to your Send Webhook as if sent. |
| `Dont Check Outbounds` | Turns off the outbound checker, so no outbound trades get cancelled. |
| `Ignore trade limit` | Keeps trying to send when Roblox says the account hit its daily trade limit, instead of moving to your next account. |
| `Show Trade Debug` | Prints the search's progress and every trade it generated. |
| `Show Scanning Users` | Prints which item's owners are being scanned, which users have trading on, and users skipped because you traded with them recently. |
| `Show Scanning Inventory` | Prints items skipped from an inventory (NFT/NFR, duplicates) and users skipped for having too few items. |

## Testing a config
```
Dont Send Trades = True
Dont Check Outbounds = True
```
Turn on both. Without `Dont Check Outbounds`, your real outbound trades get checked against the test config, and can be cancelled.
