import functools
from handler.handle_logs import log
from handler.exceptions_types import ConfigError

import configparser
import os
import shutil


@functools.lru_cache(maxsize=256)
def _convert_gain(gain):
    """
    Convert gain to a float or int; gains between -1 and 1 are percentages.
    Cached: trade generation checks the same few settings millions of times.
    """
    try:
        gain = float(gain) if "." in str(gain) else int(gain)

        if gain == 0.0:
            return gain, False

        return gain, abs(gain) < 1  # True if between -1 and 1 (percentage)
    except ValueError:
        raise ValueError(f"Invalid gain value: {gain}")


def _positive_number(value, default):
    """A setting that must be a number above 0; anything else (missing, "Not Set",
    a typo like "10m", 0 or negative) falls back to the default."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return value
    return default


def item_number(item_id) -> str:
    """The plain ID of an item: "1:1029025" (item) and "2:939596" (bundle) -> the number."""
    return str(item_id).strip().split(":")[-1]


def _item_ids(values):
    """
    NFT/NFR entries as plain IDs. Items and bundles are told apart by the
    inventory, so no "2:" is needed (old "1:"/"2:" entries still work).
    """
    return [item_number(value) for value in values or [] if str(value).strip()]


def on_item_list(item_id, ids) -> bool:
    """True when the item (an item or a bundle) is in an NFT/NFR list."""
    number = item_number(item_id)
    return any(item_number(entry) == number for entry in ids or [])


# [Inbound Settings] gain -> the [Trading Settings] key it replaces for inbounds
INBOUND_GAINS = {
    ("Inbound Settings", "Minimum RAP Gain"): "Minimum_RAP_Gain",
    ("Inbound Settings", "Maximum RAP Gain"): "Maximum_RAP_Gain",
    ("Inbound Settings", "Minimum Value Gain"): "Minimum_Value_Gain",
    ("Inbound Settings", "Maximum Value Gain"): "Maximum_Value_Gain",
    ("Inbound Settings", "Minimum Overall Value Gain"): "Minimum_Overall_Gain",
    ("Inbound Settings", "Maximum Overall Value Gain"): "Maximum_Overall_Gain",
    ("Inbound Settings", "Minimum Rap Algorithm Gain"): "Minimum_Algo_Gain",
    ("Inbound Settings", "Maximum Rap Algorithm Gain"): "Maximum_Algo_Gain",
}


DEFAULT_CONFIG = "config.default.cfg"


def create_config(filename="config.cfg", default=DEFAULT_CONFIG) -> bool:
    """
    Makes config.cfg from config.default.cfg when it doesn't exist yet.
    config.cfg isn't in git, so pulling updates never touches your settings.
    """
    if os.path.exists(filename) or not os.path.exists(default):
        return False
    shutil.copyfile(default, filename)
    return True


def _layout():
    """
    (old section, old option) -> (new section, new option). config.cfg uses
    the new names; the code reads the old ones, so a config with either works
    (see ConfigHandler.use_new_names).
    """
    gains = {
        "Minimum Overall Value Gain": "Min Overall Profit",
        "Maximum Overall Value Gain": "Max Overall Profit",
        "Minimum Value Gain": "Min Value Profit",
        "Maximum Value Gain": "Max Value Profit",
        "Minimum RAP Gain": "Min RAP Profit",
        "Maximum RAP Gain": "Max RAP Profit",
        "Minimum Rap Algorithm Gain": "Min Algorithm Profit",
        "Maximum Rap Algorithm Gain": "Max Algorithm Profit",
    }
    sections = {
        ("Trading Settings", "Profit"): {
            **gains,
            "Skip Value Gain When No Valued Items": "Skip Value Profit If No Valued Items",
            "RAP Algorithm for Valued Items": "Algorithm For Valued Items",
        },
        ("Trading Settings", "Trade Rules"): {
            "Minimum Items on Your Side": "Min Items Yours",
            "Maximum Items on Your Side": "Max Items Yours",
            "Minimum Items on Their Side": "Min Items Theirs",
            "Maximum Items on Their Side": "Max Items Theirs",
            "Trade Robux": "Add Robux",
            "Max Robux": "Max Robux",
            "Robux Divide Percentage": "Robux Divide Percentage",
            "Min Overall Value Score Percentage": "Min Overall Score",
            "Max Overall Value Score Percentage": "Max Overall Score",
            "Min RAP Score Percentage": "Min RAP Score",
            "Max RAP Score Percentage": "Max RAP Score",
            "Minimum Value Sum Of Trade": "Min Trade Value",
            "Minimum Rap Sum Of Trade": "Min Trade RAP",
            "Trade For Faces": "Receive Faces",
            "Trade For Gears": "Receive Gears",
        },
        ("Filtering Generated Trades", "Picking Trades"): {
            "Max Seconds Spent on One User": "Max Seconds Per Account",
            "Max Seconds Spent on Generating Trades": "Max Seconds Per Trader",
            "Max Valid Trades": "Stop After Passing Trades",
            "Select Trade Using": "Pick Trade By",
            "Outbound Variety": "Outbound Variety",
        },
        ("Filtering Items", "Items"): {
            "NFT": "Never Give",
            "NFR": "Never Receive",
            "Maximum Amount of Duplicate Items": "Max Duplicates Owned",
            "Maximum Amount of Trader Duplicate Items": "Max Duplicates From Trader",
            "Minimum Valued Item Demand": "Min Demand",
            "Minimum Daily Sales of Item": "Min Daily Sales",
            "Maximum Average Gaps in Sales": "Max Days Between Sales",
            "Sales History Days": "Sales History Days",
        },
        ("Getting Owners of Items", "Finding Traders"): {
            "Minimum Value of Item": "Min Item Value",
            "Minimum Rap of Item": "Min Item RAP",
            "Minimum Owners of Item": "Min Item Owners",
            "Minimum Demand of Item": "Min Item Demand",
            "Minimum Trend of Item": "Min Item Trend",
            "Scan Type": "Scan Type",
            "Scan Rares": "Scan Rares",
            "Scrape Rolimon Ads": "Scrape Rolimon Ads",
            "Owner Pages Per Scan": "Owner Pages Per Scan",
            "Recent Owner Days": "Recent Owner Days",
            "Remember Scanned Owners Days": "Remember Scanned Owners Days",
        },
        ("Filtering Users", "Finding Traders"): {
            "Minimum Total Items": "Min Trader Items",
        },
        ("Projected Detection", "Projected"): {
            "Detect Rolimons Projecteds": "Use Rolimons Projected Flag",
            "Check Valued Items": "Check Valued Items",
            "Maximum Graph Difference": "Max Price Rise",
            "Minimum Graph Difference": "Max Price Drop",
        },
        ("Inbound Settings", "Inbounds"): {
            **gains,
            "Accept Valid Trades": "Accept Good Trades",
            "Counter Trades": "Counter",
            "Dont Counter Wins": "Skip Countering Wins",
            "Decline If No Counter": "Decline If No Counter",
            "Maximum Amount of Duplicate Items": "Max Duplicates Owned",
            "Maximum Amount of Trader Duplicate Items": "Max Duplicates From Trader",
            "Max Counters Per Trader": "Max Counters Per Trader",
            "Instant Reply Minutes": "Bot Reply Minutes",
            "Instant Replies To Call It A Bot": "Bot Replies",
            "Counter Memory Hours": "Counter Memory Hours",
            "Check Inbounds Every Minutes": "Check Every Minutes",
        },
        ("Outbound Settings", "Outbounds"): {
            "Outbound Minimum Gain Offset to Cancel": "Overall And RAP Cancel Offset",
            "RAP Algorithm Gain Offset to Cancel": "Algorithm Cancel Offset",
            "Keep Trades Sent Before Config Change": "Keep Trades On Config Change",
            "Cancel If Receiving Item Becomes Projected": "Cancel If Receiving Projected",
            "Cancel If Sending Item Becomes Projected": "Cancel If Sending Projected",
        },
        ("debug", "Debug"): {
            name: name
            for name in (
                "Dont Send Trades", "Dont Check Outbounds", "Ignore trade limit",
                "Show Trade Debug", "Show Scanning Users", "Show Scanning Inventory",
            )
        },
    }
    return {
        (old_section, old): (new_section, new)
        for (old_section, new_section), names in sections.items()
        for old, new in names.items()
    }


LAYOUT = _layout()
# (new section, new option) -> (old section, old option), lowercased
OLD_NAMES = {
    (s.lower(), o.lower()): old for old, (s, o) in LAYOUT.items()
}
NEW_NAMES = {(s.lower(), o.lower()): new for (s, o), new in LAYOUT.items()}


class ConfigHandler:
    def __init__(self, filename="config.cfg"):
        if os.path.basename(filename) == "config.cfg":
            create_config(filename, os.path.join(os.path.dirname(filename), DEFAULT_CONFIG))
        self.config = configparser.ConfigParser()
        self.config.read(filename)
        self.use_new_names()
        # "[Section] Option" of every setting that couldn't be read
        self.invalid_settings = []

        # Load configuration values into attributes
        self.scan_items = self.load_scan_items()
        self.filter_users = self.load_filter_users()
        # self.prediction_algorithm = self.load_prediction_algorithm()
        self.trading = self.load_trading()
        self.filter_items = self.load_filter_items()
        self.filter_generated = self.load_filter_generated()
        self.projected_detection = self.load_projected_detection()
        self.inbounds = self.load_inbounds()
        self.debug = self.load_debug()
        self.discord_settings = self.load_discord()
        self.outbound = self.load_outbound()
        self.trade_ads = self.load_trade_ads()
        # self.mass_sender = self.load_mass_sender()
        # Check if config is filled out
        self.validate_config()

    def convert_gain(self, gain):
        """
        Convert gain to a float or int
        Treat gains < 1 and > -1 as percentages.
        """
        return _convert_gain(gain)

    def calculate_gain(self, gain, base_value, is_percentage):
        """
        Calculate the gain.
        Convert to percentage if required.
        """

        if base_value == 0:
            # Adjust fallback behavior as needed.
            return 0 if is_percentage else gain

        return (gain / base_value) * 100 if is_percentage else gain

    def check_gain(
        self, their_value, self_value, min_gain=False, max_gain=False, max_offset=0
    ):
        """
        Check if gain is within the specified range.
        """
        gain = their_value - self_value

        min_gain, is_min_percentage = (
            self.convert_gain(min_gain) if min_gain is not None else (None, False)
        )
        max_gain, is_max_percentage = (
            self.convert_gain(max_gain) if max_gain is not None else (None, False)
        )

        if min_gain is not None:
            min_gain = min_gain * 100 if is_min_percentage else min_gain

        if max_gain is not None:
            max_gain = max_gain * 100 if is_max_percentage else max_gain

        if max_gain is not None:
            max_gain += max_offset

        min_profit = self.calculate_gain(gain, self_value, is_min_percentage)
        max_profit = self.calculate_gain(gain, self_value, is_max_percentage)

        if min_gain is not None and max_gain is not None:
            return min_gain <= min_profit and max_gain >= max_profit
        elif max_gain is None and min_gain is None:
            return True
        elif min_gain is not None:
            return min_profit >= min_gain
        elif max_gain is not None:
            return max_profit <= max_gain
        return True

    def load_trade_ads(self):
        """[Trade Ads]: Rolimons trade ads. Missing settings use the defaults."""
        from handler.handle_trade_ads import (
            MAX_ITEMS_PER_SIDE,
            MIN_MINUTES_BETWEEN_ADS,
            OFFER_PICKS,
            REQUEST_TAGS,
        )

        section = "Trade Ads"

        def invalid(option, why):
            self.invalid_settings.append(f"{self.shown(section, option)} ({why})")

        enabled = self.get_boolean("Trade Ads", "Enabled")
        auto_login = self.get_boolean("Trade Ads", "Auto Rolimons Login")

        minutes = self.get_float_default("Trade Ads", "Post Every Minutes", 20)
        if minutes == "Not Set":
            minutes = 20
        elif minutes is None or minutes < MIN_MINUTES_BETWEEN_ADS:
            invalid(
                "Post Every Minutes",
                f"must be {MIN_MINUTES_BETWEEN_ADS} or more, Rolimons allows one "
                f"ad every {MIN_MINUTES_BETWEEN_ADS} minutes",
            )
            minutes = 20

        offer_count = self.get_int("Trade Ads", "Offer Items")
        if offer_count is None or offer_count == "Not Set":
            offer_count = MAX_ITEMS_PER_SIDE
        elif not 1 <= offer_count <= MAX_ITEMS_PER_SIDE:
            invalid("Offer Items", f"must be 1 to {MAX_ITEMS_PER_SIDE}")
            offer_count = MAX_ITEMS_PER_SIDE

        pick = self.get_string("Trade Ads", "Offer Items Using") or "highest_value"
        pick = pick.strip().lower()
        if pick not in OFFER_PICKS:
            invalid("Offer Items Using", "must be " + ", ".join(OFFER_PICKS))
            pick = "highest_value"

        def item_ids(values, option):
            ids = []
            for raw in values:
                raw = item_number(raw)
                if not raw or raw.lower() == "none":
                    continue
                if not raw.isdigit():
                    invalid(option, "must be item IDs separated by commas")
                    return []
                ids.append(int(raw))
            if len(ids) > MAX_ITEMS_PER_SIDE:
                invalid(option, f"at most {MAX_ITEMS_PER_SIDE} items")
                return ids[:MAX_ITEMS_PER_SIDE]
            return ids

        offer_items = item_ids(
            self.get_list("Trade Ads", "Offer Item IDs"), "Offer Item IDs"
        )
        if enabled is True and pick == "manual" and not offer_items:
            invalid(
                "Offer Item IDs",
                "Offer Items Using = manual needs at least one item ID here",
            )
        request_items = item_ids(
            self.get_list("Trade Ads", "Request Item IDs"), "Request Item IDs"
        )

        if self.config.has_option("Trade Ads", "Request Tags"):
            tags = [
                t.strip().lower()
                for t in self.get_list("Trade Ads", "Request Tags")
                if t.strip() and t.strip().lower() != "none"
            ]
        else:
            tags = ["any"]
        unknown = [t for t in tags if t not in REQUEST_TAGS]
        if unknown:
            invalid("Request Tags", "can only be " + ", ".join(REQUEST_TAGS))
            tags = [t for t in tags if t in REQUEST_TAGS]

        if len(request_items) + len(tags) > MAX_ITEMS_PER_SIDE:
            invalid(
                "Request Item IDs",
                f"Request Item IDs and Request Tags together can be at most "
                f"{MAX_ITEMS_PER_SIDE}",
            )
        # outbound ads always request the other person's items
        if enabled is True and pick != "outbound" and not request_items and not tags:
            invalid("Request Tags", "an ad needs at least one request item or tag")

        return {
            "Enabled": bool(enabled) and enabled != "Not Set",
            # On unless set to False
            "Auto_Rolimons_Login": auto_login is not False,
            "Post_Every_Minutes": minutes,
            "Offer_Items": offer_count,
            "Offer_Items_Using": pick,
            "Offer_Item_IDs": offer_items,
            "Request_Items": request_items,
            "Request_Tags": tags,
        }

    def load_outbound(self):
        return {
            # Trades sent before the config last changed are only cancelled if
            # they're losing overall (or receive a projected item), not for
            # failing the new config's rules. Older configs use the old name.
            "Only_Cancel_Losing_After_Config_Change": bool(
                self.get_boolean(
                    "Outbound Settings", "Keep Trades Sent Before Config Change"
                )
                if self.config.has_option(
                    "Outbound Settings", "Keep Trades Sent Before Config Change"
                )
                else self.get_boolean(
                    "Outbound Settings", "Only Cancel Losing Trades After Config Change"
                )
            ),
            # Missing in older configs = True (how it always worked)
            "Cancel_Receiving_Projected": self.get_boolean(
                "Outbound Settings", "Cancel If Receiving Item Becomes Projected"
            )
            is not False,
            # Missing = False
            "Cancel_Sending_Projected": self.get_boolean(
                "Outbound Settings", "Cancel If Sending Item Becomes Projected"
            )
            is True,
        }

    def load_discord(self):
        return {
            "Send_Webhook": self.get_string("Discord", "Send Webhook"),
            "Completed_Webhook": self.get_string("Discord", "Completed Webhook"),
            # Optional: where crashes and account problems get posted
            "Error_Webhook": self.get_string("Discord", "Error Webhook"),
            # Missing = True: keep the bot accounts' names out of Discord
            "Hide_Username": self.get_boolean("Discord", "Hide Username") is not False,
        }

    def load_scan_items(self):
        return {
            "Minimum_Value_of_Item": self.get_int(
                "Getting Owners of Items", "Minimum Value of Item"
            ),
            "Minimum_Rap_of_Item": self.get_int(
                "Getting Owners of Items", "Minimum Rap of Item"
            ),
            "Minimum_Owners_of_Item": self.get_int(
                "Getting Owners of Items", "Minimum Owners of Item"
            ),
            "Minimum_Demand_of_Item": self.get_int(
                "Getting Owners of Items", "Minimum Demand of Item"
            ),
            "Minimum_Trend_of_Item": self.get_int(
                "Getting Owners of Items", "Minimum Trend of Item"
            ),
            "Scan_Rares": self.get_boolean("Getting Owners of Items", "Scan Rares"),
            "Scan_Type": self.get_string("Getting Owners of Items", "Scan Type"),
            # Missing in older configs = these defaults
            "Owner_Pages_Per_Scan": self.get_int_default(
                "Getting Owners of Items", "Owner Pages Per Scan", 2
            ),
            "Recent_Owner_Days": self.get_float_default(
                "Getting Owners of Items", "Recent Owner Days", 7
            ),
            "Remember_Scanned_Owners_Days": self.get_float_default(
                "Getting Owners of Items", "Remember Scanned Owners Days", 3
            ),
            "Scrape_Rolimon_Ads": self.get_boolean(
                "Getting Owners of Items", "Scrape Rolimon Ads"
            ),
        }

    def load_filter_users(self):
        return {
            "Minimum_Total_Items": self.get_int(
                "Filtering Users", "Minimum Total Items"
            ),
        }

    def load_debug(self):
        return {
            "trading_debug": self.get_boolean("debug", "Show Trade Debug"),
            "ignore_limit": self.get_boolean("debug", "Ignore trade limit"),
            "dont_send_trade": self.get_boolean("debug", "Dont Send Trades"),
            "dont_check_outbounds": self.get_boolean("debug", "Dont Check Outbounds"),
            "show_scanning_users": self.get_boolean("debug", "Show Scanning Users"),
            "show_scanning_inventory": self.get_boolean(
                "debug", "Show Scanning Inventory"
            ),
        }

    # def load_prediction_algorithm(self):
    #    return {
    #        'Predict_Values_of_Your_Inventory': self.get_string('Prediction Algorithm', 'Predict Values of your Inventory'),
    #        'Predict_Values_of_Their_Inventory': self.get_string('Prediction Algorithm', 'Predict Values of their Inventory'),
    #        'Max_Over_Pay': self.get_float('Prediction Algorithm', 'Max Over Pay'),
    #        'Max_Loss': self.get_float('Prediction Algorithm', 'Max Loss'),
    #        'NFT_from_Prediction': self.get_list_of_ints('Prediction Algorithm', 'NFT from Prediction'),
    #        'Minimum_Value_to_predict': self.get_int('Prediction Algorithm', 'Minimum Value to predict'),
    #        'Maximum_Value_to_predict': self.get_int('Prediction Algorithm', 'Maximum Value to predict')
    #    }

    def load_filter_items(self):
        return {
            "NFT": _item_ids(self.get_list("Filtering Items", "NFT")),
            "NFR": _item_ids(self.get_list("Filtering Items", "NFR")),
            "Maximum_Amount_of_Duplicate_Items": self.get_int(
                "Filtering Items", "Maximum Amount of Duplicate Items"
            ),
            "Maximum_Amount_of_Trader_Duplicate_Items": self.get_int(
                "Filtering Items", "Maximum Amount of Trader Duplicate Items"
            ),
            "MinDemand": self.get_int("Filtering Items", "Minimum Valued Item Demand"),
            "MinDailySales": self.get_float(
                "Filtering Items", "Minimum Daily Sales of Item"
            ),
            "MaxSalesGap": self.get_float(
                "Filtering Items", "Maximum Average Gaps in Sales"
            ),
            # How many days of sales history RAP Algorithm, daily sales and
            # sales gaps use (older sales would drag them toward old prices)
            "Sales_History_Days": self.load_sales_history_days(),
        }

    def load_sales_history_days(self):
        days = self.get_int_default("Filtering Items", "Sales History Days", 90)
        if days == "Not Set":
            return 90
        if days is None or days < 1:
            self.invalid_settings.append(
                f"{self.shown('Filtering Items', 'Sales History Days')} (must be a whole number above 0)"
            )
            return 90
        return days

    def load_filter_generated(self):
        return {
            "Max_Seconds_Spent_on_One_User": self.get_float(
                "Filtering Generated Trades", "Max Seconds Spent on One User"
            ),
            "Max_Seconds_Spent_on_Generating_Trades": self.get_float_default(
                "Filtering Generated Trades", "Max Seconds Spent on Generating Trades", 600
            ),
            "Max_Valid_Trades": self.get_float(
                "Filtering Generated Trades", "Max Valid Trades"
            ),
            "Select_Trade_Using": self.get_string(
                "Filtering Generated Trades", "Select Trade Using"
            ),
            "Outbound_Variety": self._outbound_variety(),
        }

    def _outbound_variety(self):
        """0 (off) to 1. Missing or None = 0."""
        section, option = "Filtering Generated Trades", "Outbound Variety"
        value = self.get_float_default(section, option, 0.0)
        if value is None or value == "Not Set":  # "Not Set" is already reported
            return 0.0
        if not 0 <= value <= 1:
            self.invalid_settings.append(
                f"{self.shown(section, option)} (must be between 0 and 1)"
            )
            return 0.0
        return value

    # Where each load_trading setting lives in config.cfg (for writing an
    # account's config back into config.cfg)
    TRADING_OPTIONS = {
        "Outbound_Cancel_Offset": ("Outbound Settings", "Outbound Minimum Gain Offset to Cancel"),
        "Algo_Cancel_Offset": ("Outbound Settings", "RAP Algorithm Gain Offset to Cancel"),
        "Minimum_RAP_Gain": ("Trading Settings", "Minimum RAP Gain"),
        "Maximum_RAP_Gain": ("Trading Settings", "Maximum RAP Gain"),
        "Minimum_Value_Gain": ("Trading Settings", "Minimum Value Gain"),
        "Maximum_Value_Gain": ("Trading Settings", "Maximum Value Gain"),
        "Skip_Value_Gain_Without_Valued": ("Trading Settings", "Skip Value Gain When No Valued Items"),
        "Minimum_Overall_Gain": ("Trading Settings", "Minimum Overall Value Gain"),
        "Maximum_Overall_Gain": ("Trading Settings", "Maximum Overall Value Gain"),
        "Rap_Algo_For_Valued": ("Trading Settings", "RAP Algorithm for Valued Items"),
        "Minimum_Algo_Gain": ("Trading Settings", "Minimum Rap Algorithm Gain"),
        "Maximum_Algo_Gain": ("Trading Settings", "Maximum Rap Algorithm Gain"),
        "TradeRobux": ("Trading Settings", "Trade Robux"),
        "RobuxDividePercentage": ("Trading Settings", "Robux Divide Percentage"),
        "MaxRobux": ("Trading Settings", "Max Robux"),
        "MinOverallValueScorePercentage": ("Trading Settings", "Min Overall Value Score Percentage"),
        "MaxOverallValueScorePercentage": ("Trading Settings", "Max Overall Value Score Percentage"),
        "MinRAPScorePercentage": ("Trading Settings", "Min RAP Score Percentage"),
        "MaxRAPScorePercentage": ("Trading Settings", "Max RAP Score Percentage"),
        "MinimumItemsYourSide": ("Trading Settings", "Minimum Items on Your Side"),
        "MaximumItemsYourSide": ("Trading Settings", "Maximum Items on Your Side"),
        "MinimumItemsTheirSide": ("Trading Settings", "Minimum Items on Their Side"),
        "MaximumItemsTheirSide": ("Trading Settings", "Maximum Items on Their Side"),
        "MinimumValueOfTrade": ("Trading Settings", "Minimum Value Sum Of Trade"),
        "MinimumRapOfTrade": ("Trading Settings", "Minimum Rap Sum Of Trade"),
        "TradeForFaces": ("Trading Settings", "Trade For Faces"),
        "TradeForGears": ("Trading Settings", "Trade For Gears"),
    }
    ITEMS_OPTIONS = {
        "NFT": ("Filtering Items", "NFT"),
        "NFR": ("Filtering Items", "NFR"),
        "Maximum_Amount_of_Duplicate_Items": ("Filtering Items", "Maximum Amount of Duplicate Items"),
        "Maximum_Amount_of_Trader_Duplicate_Items": ("Filtering Items", "Maximum Amount of Trader Duplicate Items"),
        "MinDemand": ("Filtering Items", "Minimum Valued Item Demand"),
        "MinDailySales": ("Filtering Items", "Minimum Daily Sales of Item"),
        "MaxSalesGap": ("Filtering Items", "Maximum Average Gaps in Sales"),
    }
    PICKING_OPTIONS = {
        "Max_Seconds_Spent_on_One_User": ("Filtering Generated Trades", "Max Seconds Spent on One User"),
        "Max_Seconds_Spent_on_Generating_Trades": ("Filtering Generated Trades", "Max Seconds Spent on Generating Trades"),
        "Max_Valid_Trades": ("Filtering Generated Trades", "Max Valid Trades"),
        "Select_Trade_Using": ("Filtering Generated Trades", "Select Trade Using"),
        "Outbound_Variety": ("Filtering Generated Trades", "Outbound Variety"),
    }
    def load_trading(self):
        return {
            # Between 0 and 1 = a share of the minimum, otherwise Robux
            "Outbound_Cancel_Offset": self.get_float(
                "Outbound Settings", "Outbound Minimum Gain Offset to Cancel"
            ),
            "Algo_Cancel_Offset": self.get_float(
                "Outbound Settings", "RAP Algorithm Gain Offset to Cancel"
            ),
            "Minimum_RAP_Gain": self.get_float("Trading Settings", "Minimum RAP Gain"),
            "Maximum_RAP_Gain": self.get_float("Trading Settings", "Maximum RAP Gain"),
            "Minimum_Value_Gain": self.get_float(
                "Trading Settings", "Minimum Value Gain"
            ),
            "Maximum_Value_Gain": self.get_float(
                "Trading Settings", "Maximum Value Gain"
            ),
            # Missing in older configs = off
            "Skip_Value_Gain_Without_Valued": bool(
                self.get_boolean("Trading Settings", "Skip Value Gain When No Valued Items")
            ),
            "Minimum_Overall_Gain": self.get_float(
                "Trading Settings", "Minimum Overall Value Gain"
            ),
            "Maximum_Overall_Gain": self.get_float(
                "Trading Settings", "Maximum Overall Value Gain"
            ),
            "Rap_Algo_For_Valued": self.get_string(
                "Trading Settings", "RAP Algorithm for Valued Items"
            ),
            "Minimum_Algo_Gain": self.get_float(
                "Trading Settings", "Minimum Rap Algorithm Gain"
            ),
            "Maximum_Algo_Gain": self.get_float(
                "Trading Settings", "Maximum Rap Algorithm Gain"
            ),
            "TradeRobux": self.get_boolean("Trading Settings", "Trade Robux"),
            "RobuxDividePercentage": self.get_float(
                "Trading Settings", "Robux Divide Percentage"
            ),
            "MaxRobux": self.get_float("Trading Settings", "Max Robux"),
            "MinOverallValueScorePercentage": self.get_float(
                "Trading Settings", "Min Overall Value Score Percentage"
            ),
            "MaxOverallValueScorePercentage": self.get_float(
                "Trading Settings", "Max Overall Value Score Percentage"
            ),
            "MinRAPScorePercentage": self.get_float(
                "Trading Settings", "Min RAP Score Percentage"
            ),
            "MaxRAPScorePercentage": self.get_float(
                "Trading Settings", "Max RAP Score Percentage"
            ),
            "MinimumItemsYourSide": self.get_int(
                "Trading Settings", "Minimum Items on Your Side"
            ),
            "MaximumItemsYourSide": self.get_int(
                "Trading Settings", "Maximum Items on Your Side"
            ),
            "MinimumItemsTheirSide": self.get_int(
                "Trading Settings", "Minimum Items on Their Side"
            ),
            "MaximumItemsTheirSide": self.get_int(
                "Trading Settings", "Maximum Items on Their Side"
            ),
            "MinimumValueOfTrade": self.get_float(
                "Trading Settings", "Minimum Value Sum Of Trade"
            ),
            "MinimumRapOfTrade": self.get_float(
                "Trading Settings", "Minimum Rap Sum Of Trade"
            ),
            "TradeForFaces": self.get_boolean("Trading Settings", "Trade For Faces"),
            "TradeForGears": self.get_boolean("Trading Settings", "Trade For Gears"),
        }

    def load_inbounds(self):
        return {
            "CounterTrades": self.get_boolean("Inbound Settings", "Counter Trades"),
            "Dont_Counter_Wins": self.get_boolean(
                "Inbound Settings", "Dont Counter Wins"
            ),
            # On unless set to False
            "Decline_If_No_Counter": self.get_boolean(
                "Inbound Settings", "Decline If No Counter"
            )
            is not False,
            # Off unless set: accepting a trade can't be undone
            "Accept_Valid_Trades": bool(
                self.get_boolean("Inbound Settings", "Accept Valid Trades")
            ),
            "Check_Every_Minutes": _positive_number(
                self.get_float("Inbound Settings", "Check Inbounds Every Minutes"), 30
            ),
            "Gains": self.load_inbound_gains(),
            # Counter loops (missing = these defaults, 0 = off)
            "Max_Counters_Per_Trader": self._whole_number(
                "Inbound Settings", "Max Counters Per Trader", 3
            ),
            "Instant_Reply_Seconds": 60
            * _positive_number(
                self.get_float_default("Inbound Settings", "Instant Reply Minutes", 20),
                20,
            ),
            "Instant_Replies_For_Bot": self._whole_number(
                "Inbound Settings", "Instant Replies To Call It A Bot", 3
            ),
            # Duplicates for inbounds (accepting and counters); missing = 2
            "Max_Duplicates": self._whole_number(
                "Inbound Settings", "Maximum Amount of Duplicate Items", 2
            ),
            "Max_Trader_Duplicates": self._whole_number(
                "Inbound Settings", "Maximum Amount of Trader Duplicate Items", 2
            ),
            "Counter_Memory_Hours": _positive_number(
                self.get_float_default("Inbound Settings", "Counter Memory Hours", 24),
                24,
            ),
        }

    def _whole_number(self, section, option, default) -> int:
        """A whole number setting: missing = default, None = 0 (off)."""
        if not self.config.has_option(section, option):
            return default
        if str(self.get_string(section, option)).strip().lower() in ("none", "false"):
            return 0
        value = self.get_int(section, option)
        return value if isinstance(value, int) and value >= 0 else default

    def load_inbound_gains(self) -> dict:
        """
        [Inbound Settings] gains, for accepting and countering. Only the ones
        that are set: the rest use [Trading Settings] (or the account's config).
        """
        gains = {
            key: self.get_float(section, option)
            for (section, option), key in INBOUND_GAINS.items()
            if self.config.has_option(section, option)
        }
        return gains

    def load_projected_detection(self):
        return {
            "Detect_Rolimons_Projecteds": self.get_boolean(
                "Projected Detection", "Detect Rolimons Projecteds"
            ),
            # Missing = today's default (40% each way); None = don't check that way
            "MaximumGraphDifference": self.get_float_default(
                "Projected Detection", "Maximum Graph Difference", 0.4
            ),
            "MinimumGraphDifference": self.get_float_default(
                "Projected Detection", "Minimum Graph Difference", -0.4
            ),
            "MinPriceDifference": self.get_float(
                "Projected Detection", "MinPriceDifference"
            ),
            # Valued items are priced by Rolimons, not sales: off (and missing)
            # = they're never treated as projected
            "Check_Valued_Items": self.get_boolean(
                "Projected Detection", "Check Valued Items"
            ) is True,
        }

    def load_mass_sender(self):
        return {
            "Enable_Mass_Sending": self.get_boolean(
                "Mass Sender", "Enable Mass Sending"
            ),
            "Always_send": self.get_list_of_ints("Mass Sender", "Always send"),
            "Always_Receive": self.get_list_of_ints("Mass Sender", "Always Receive"),
        }

    def get_int(self, section, option):
        try:
            return (
                self.config.getint(section, option)
                if self.config.has_option(section, option)
                else None
            )
        except (ValueError, TypeError) as e:
            log(f"[CONFIG] {self.shown(section, option)} must be a whole number: {e}")
            self.invalid_settings.append(
                f"{self.shown(section, option)} (must be a whole number)"
            )
            return "Not Set"

    def get_float(self, section, option):
        try:
            return (
                self.config.getfloat(section, option)
                if self.config.has_option(section, option)
                else None
            )
        except (ValueError, TypeError):
            # log(f"Error retrieving float for [{section}] {option}: {e}")
            try:
                string = self.get_string(section, option)
                if string.lower() == "false" or string.lower() == "none":
                    return None
            except (AttributeError, ValueError, TypeError):
                pass
            self.invalid_settings.append(
                f"{self.shown(section, option)} (must be a number or None)"
            )
            return "Not Set"

    def get_int_default(self, section, option, default):
        """Like get_int, but a missing setting gets `default`."""
        if not self.config.has_option(section, option):
            return default
        return self.get_int(section, option)

    def get_float_default(self, section, option, default):
        """Like get_float, but a missing setting gets `default` (None still means off)."""
        if not self.config.has_option(section, option):
            return default
        return self.get_float(section, option)

    def get_string(self, section, option):
        try:
            return (
                self.config.get(section, option)
                if self.config.has_option(section, option)
                else None
            )
        except (ValueError, TypeError) as e:
            log(f"[CONFIG] Couldn't read {self.shown(section, option)}: {e}")
            self.invalid_settings.append(f"{self.shown(section, option)}")
            return "Not Set"

    def get_boolean(self, section, option):
        try:
            return (
                self.config.getboolean(section, option)
                if self.config.has_option(section, option)
                else None
            )
        except (ValueError, TypeError) as e:
            log(f"[CONFIG] {self.shown(section, option)} must be True or False: {e}")
            self.invalid_settings.append(
                f"{self.shown(section, option)} (must be True or False)"
            )
            return "Not Set"

    def get_list(self, section, option):
        try:
            if self.config.has_option(section, option):
                values = self.config.get(section, option).split(",")

                # Filter out invalid values (None or empty string)
                valid_values = [v for v in values if v and v != "None"]

                return valid_values
            return []
        except (ValueError, TypeError) as e:
            log(f"[CONFIG] {self.shown(section, option)} must be a list of whole numbers: {e}")
            return []

    def use_new_names(self):
        """
        Copies settings written with the new names ([Profit] Min Overall
        Profit...) to the old names the code reads. A config with the old
        names works as before. If both are there, the new one wins.
        """
        self.new_names = False
        # Old name -> how the file writes it, for messages
        self.written_names = {}
        for (new_section, new_option), (old_section, old_option) in OLD_NAMES.items():
            section = next(
                (s for s in self.config.sections() if s.lower() == new_section), None
            )
            if section is None or not self.config.has_option(section, new_option):
                continue
            self.new_names = True
            written = NEW_NAMES[(old_section.lower(), old_option.lower())][1]
            self.written_names[(old_section.lower(), old_option.lower())] = (
                f"[{section}] {written}"
            )
            if not self.config.has_section(old_section):
                self.config.add_section(old_section)
            self.config.set(
                old_section, old_option, self.config.get(section, new_option, raw=True)
            )

    def shown(self, section, option) -> str:
        """A setting's name the way the config file writes it, for messages."""
        written = getattr(self, "written_names", {}).get((section.lower(), option.lower()))
        if written:
            return written
        if getattr(self, "new_names", False):
            # Not in the file at all: name it the new way
            new = NEW_NAMES.get((section.lower(), option.lower()))
            if new:
                return f"[{new[0]}] {new[1]}"
        return f"[{section}] {option}"

    def validate_config(self):
        # Any setting that couldn't be read, named the way it's written in the file
        if self.invalid_settings:
            raise ConfigError(
                "These config settings are invalid: "
                + "; ".join(dict.fromkeys(self.invalid_settings))
            )
        for section in [
            self.scan_items,
            self.filter_users,
            self.trading,
            self.projected_detection,
        ]:
            for key, value in section.items():
                if value == "Not Set":
                    raise ConfigError(
                        f"Configuration error: '{key}' is missing or invalid."
                    )
