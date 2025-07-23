# DOGGO TRADE BOT
[![Roblox](https://img.shields.io/badge/Roblox-00A2FF?style=for-the-badge&logo=roblox&logoColor=white)](https://www.roblox.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff&style=for-the-badge)](#)

A roblox trading bot, automates roblox's player-to-player trading system. It scrapes trading websites to get values of items then can generate winning trades and mass send them to other roblox users.
>    [!WARNING]
>  This bot is for eductional purposes and my first big python project, I would rewrite most of the complex functions and handle errors if I invested more time into this bot.


This bot used to be a paid service that im releasing, because I dont intend on updating or rewriting the code.
# Features
### Quality of life
- Multiple Cookie Management: Add multiple cookies to trade on and alert when premium expires.
- Projected Detection: Identify potentially manipulated items
- Outbound Checker: Cancel Losing outbounds
- Auto Account Setup: Can login through the browser and the bot will automatically take your cookie.

### Trading Features
- Value Trading: Integrates with Rolimons value data
- RAP Trading: Integrates with Roblox Recent-Average-Price values
- RAP Algorithm: Algorithm imported from [OTB](https://github.com/pydlv/otb-legacy) to determine the real recent RAP using an algorithm
- 2FA Verifier: Solves 2FA challenge to allow trading
- Inbound Checker: Can counter/accept inbound trades (Might have to enable it in source-code)
- Duplicate Control: Prevent accumulating too many identical items

### 📊 Advanced Filtering
- Item Quality: Filter by demand levels (Terrible to Amazing)
- Market Activity: Minimum daily sales and gap analysis
- User Requirements: Minimum inventory size and item count


# 🚀 Installation
If you download the exe skip these steps
### 1. Clone this repo
```bash
git clone https://github.com/Flaried/TradebotRBX.git
cd TradebotRBX
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

### Setup
Video Tutorial (skip to 0:12): https://youtu.be/2SdEivsw8yA?si=kvisNUJGlJV0dyZ9&t=12

After you got the application built, you have to add an account and 2fa authorization secret.

Launch the application and then go to account manager.

Theres two built-in ways of doing this, Automatic browser login or Manual Setup, 

for automatic login give it your 2fa authorzation secret from ROBLOX (shown in video) and then login to your account through the browser and it will add that account

if that didn't work you can manually input the 2fa authorzation secret and cookie and it will make an entry into the json file.



# Config Guide
In this repo ive given basic configs, but if you want to make your own heres the important notes:
```
Minimum RAP Gain = 150
Maximum RAP Gain = None

#NOTE: The way its calculate: Shaggy overall value would be its RAP (instead of being 0 because it has no value like in value gain)
# and Dominus Emp: Overall Value = its value (Because its valued)
Minimum Overall Value Gain = 0
Maximum Overall Value Gain = 300

Minimum Value Gain = 0
Maximum Value Gain = None
```
> [!WARNING] 
> a trade is only sent if it meets ALL THREE gain requirements simultaneously. 
> 
> THESE values are all INDEPENDANT when calculating the total profit. Meaning you can profit 0 value and 3000 RAP because there is no value items in the trade.
>
> An example of this would be that if min value gain was 1, it could ONLY send trades with VALUED items.


Set most these values to None, because if your config is strict or not possible it wont send trades.

`RAP Algorithm for Valued Items = ""` 

This setting is for how the RAP algorithm is applied to different items, should it apply to RAP items only? or Valued Items, if you dont understand this setting the RAP algorithm could be unpredictable.

When the bot prints `Couldnt find valid_trades heres invalid trades reasons:` it means its went through all the trades and couldn't generate one based on the values above, and it will have a count. 

For example if its invalid reason value_gain: 900 it means your value gain was impossible to satisfy,

if one value keeps coming up and you get no trades that means either most of your items are trade-locked or that value is impossible to be met in that case, and you NEED to change your config.
# Credits
Source code for RAP algorithm taken from https://github.com/pydlv/otb-legacy

 


