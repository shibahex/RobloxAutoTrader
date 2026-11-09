# Multi-account Trading Bot
[![Roblox](https://img.shields.io/badge/Roblox-00A2FF?style=for-the-badge&logo=roblox&logoColor=white)](https://www.roblox.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff&style=for-the-badge)](#)

https://discord.gg/aR7pYBcqHn - The Discord Server for this program!

A roblox trading bot, automates roblox's player-to-player trading system. It scrapes trading websites to get values of items then can generate winning trades and mass send them to other roblox users.
>    [!WARNING]
>  This bot is for eductional purposes and my first big python project, I would rewrite most of the complex functions and handle errors if I invested more time into this bot.
<img width="..." height="276" alt="trade1" src="https://github.com/user-attachments/assets/f5941354-2576-4cb3-ad4f-28abeb5889b5" />

<img width="..." height="276" alt="trade2" src="https://github.com/user-attachments/assets/a3427f47-f6b8-4f1b-b9da-95e47fcabf04" />

This bot used to be a paid service that im releasing, because I dont intend on updating or rewriting the code.
# Features
### 🛠️ Quality of life
- Multiple Cookie Management: Add multiple cookies to trade on and alert when premium expires.
- Projected Detection: Identify potentially manipulated items
- Outbound Checker: Cancels outbounds that turn into losses or would give you a projected item, re-checked every time Rolimons updates
- Auto Account Setup: Can login through the browser and the bot will automatically take your cookie.
- Clear Config Errors: A setting with a typo stops the bot at startup and tells you which one
- Prebuilt Downloads: Windows .exe and Linux binary with every release

### 🔄 Trading Features
- Value Trading: Integrates with Rolimons value data
- RAP Trading: Integrates with Roblox Recent-Average-Price values
- RAP Algorithm: Algorithm imported from [OTB](https://github.com/pydlv/otb-legacy) to determine the real recent RAP using an algorithm
- 2FA Verifier: Solves 2FA challenge to allow trading
- Inbound Checker: Accepts inbound trades that pass your config and counters the rest (both optional)
- Rolimons Trade Ads: Posts trade ads for your accounts to bring in more inbounds
- Outbound Variety: Spreads your items across outbounds, so one accepted trade doesn't make the rest invalid
- Duplicate Control: Prevent accumulating too many identical items

### 📊 Advanced Filtering
- Item Quality: Filter by demand levels (Terrible to Amazing)
- Market Activity: Minimum daily sales and gap analysis
- User Requirements: Minimum inventory size and item count


#  Installation
If you download the [latest release](https://github.com/shibahex/RobloxAutoTrader/releases/latest) (Windows .exe or Linux binary), skip these steps
### 1. Clone this repo
```bash
git clone https://github.com/shibahex/RobloxAutoTrader.git
cd RobloxAutoTrader
```

> [!NOTE]
> I recommend using a python virtual environment before using pip
### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the program
```bash
python main.py
```

### Updating
The main menu tells you when a new version is out, and how to get it. From a clone:
```bash
git pull
pip install -r requirements.txt
```
Your `config.cfg` isn't in git (the bot makes it from `config.default.cfg` the first time it runs), so pulling never touches your settings. Clones from before this change get one-time commands from the bot instead, which keep your `config.cfg`.

### Setup
Video (skip to 0:12): https://youtu.be/2SdEivsw8yA?si=kvisNUJGlJV0dyZ9&t=12
#### Adding an Account and 2FA Authorization Secret
Theres two built-in ways of doing this in account manager, automatic browser login or manual setup, 

for automatic login give it your 2FA Secret Code from ROBLOX (shown in video) and then login to your account through the browser and it will add that account

if that didn't work you can manually input the 2FA Secret Code and cookie and it will make an entry into the json file.



# Config Guide
**Full guide: [docs/config/README.md](docs/config/README.md)**, every section and setting explained.

The bot reads `config.cfg` (made from `config.default.cfg` the first time it runs). Every setting has a note above it explaining what it does.

> [!IMPORTANT]
> **`[Profit]` and `[Trade Rules]` decide which trades get sent.** Everything else is tweaking: who the bot looks for, how fast it searches, and how it handles inbound and outbound trades.

### Picking a config
`configs/` has ready-made presets. To use one: **Config Manager > Use a preset for config.cfg**, then pick a preset. It's copied over your `config.cfg`.

| Preset | Trades for |
|---|---|
| `rap_config.cfg` | RAP items only |
| `rap_algorithm.cfg` | RAP items, judged by the RAP Algorithm. Don't use with valued items |
| `small_value.cfg` | Inventories worth about 10–30k, with valued and RAP items |
| `big_value.cfg` | Inventories with lots of valued items (50k+ Value) |
| `rap_to_value.cfg` | Trading RAP items into valued items |
| `value_to_rap.cfg` | Trading valued items for RAP wins |

To change `config.cfg` without opening the file, use **Config Manager > Edit config.cfg**: pick a section and a setting, and it shows the setting's notes and the easiest way to change it (a numbered list for settings with a few options, True/False, add/remove for item lists like `Never Give` by ID or name, on/off for tags, and a builder for `Pick Trade By`). Comments are kept, the old file is saved as `config.backup.cfg`, and a change that would stop the config from loading isn't saved.

To give one account its own settings, use **Config Manager > Account configs**, pick the account, then a section (`[Profit]`, `[Trade Rules]`, `[Items]`, `[Picking Trades]`, `[Outbounds]` offsets). An account config only holds the settings you change there; everything else comes from `config.cfg`.

### The 4 numbers
| | What it is |
|---|---|
| **RAP** | Roblox's recent average price |
| **Value** | The Rolimons value. Items without one count as **0** |
| **Overall Value** | The Rolimons value if the item has one, otherwise its RAP |
| **RAP Algorithm** | The bot's estimate of what an item really sells for, from its sales history |

**Gain** = what you receive minus what you give. A trade is only sent if it passes **every** gain setting, and each one is checked on its own. A trade of RAP items can be +3000 RAP and still be 0 Value gain, so `Minimum Value Gain = 1` means only trades with valued items get sent.

A gain between -1 and 1 is a percentage of your side: `0.1` = 10%.

### Rules that trip people up
- `None` turns a setting off, but only where the note says so. Settings marked **whole number** must be a whole number, or the bot won't start.
- The stricter the config, the fewer trades get sent. Start loose, then tighten.
- `Accept Good Trades` accepts inbound trades automatically, which can't be undone. Leave it off until your minimum gains are set the way you want.
- Changing your config can cancel outbound trades that don't pass the new settings. `Keep Trades Sent Before Config Change = True` stops that.

### No trades getting sent?
If the bot prints `Couldnt find valid_trades heres invalid trades reasons:`, it checked every trade with that person and none passed. The numbers show which setting blocked them most:

| Reason | Setting to loosen |
|---|---|
| `rap_gain` | Minimum / Max RAP Profit |
| `value_gain` | Minimum / Max Value Profit |
| `overall_gain` | Minimum / Max Overall Profit |
| `algo_gain` | Minimum / Max Algorithm Profit |
| `overall_close_percentage` | Min / Max Overall Score |
| `rap_close_percentage` | Min / Max RAP Score |
| `min_value_of_trade` | Min Trade Value |
| `min_rap_of_trade` | Min Trade RAP |

If one reason is far ahead of the rest on every user, that setting is too strict for your inventory. If the counts are all low, most of your items are probably on trade hold.

### Testing a config
Set these in `[Debug]`, run the bot, and watch what it would send:
```
Dont Send Trades = True
Dont Check Outbounds = True
```
`Dont Check Outbounds` matters: without it, your real outbound trades get checked against the test config and can be cancelled.

# Credits
Source code for RAP algorithm taken from https://github.com/pydlv/otb-legacy

 


