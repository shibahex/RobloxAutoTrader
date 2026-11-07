[← Config guide](README.md)

# [Discord]

Webhook URLs. Leave one empty to turn it off.

| Setting | Posts when |
|---|---|
| `Send Webhook` | A trade is sent (blue), an inbound is countered (yellow), or an inbound is declined because no counter passed your gains (red) |
| `Completed Webhook` | A trade completes, or the bot accepts an inbound (green, posted once) |
| `Error Webhook` | The bot hits an error, or an account stops working (for example, an expired cookie) |
| `Hide Username` | `True` (default) keeps your bot accounts' usernames out of Discord: webhook footers show only the other trader's ID, and error alerts say "account 1", "account 2" (Account Manager numbers) instead. `False` shows them. |
