from collections import Counter
from handler.handle_config import ConfigHandler
from itertools import combinations
import math
import random
import time
from handler.handle_logs import log


# Their side's combinations are worked out once and reused when there are at
# most this many (about 30 items, up to 4 per side); bigger ones are made as needed
MAX_CACHED_COMBINATIONS = 50_000


# Every "Select Trade Using" value select_trade understands
SELECT_TRADE_OPTIONS = (
    "lowest_demand",
    "random",
    "highest_volume_gain",
    "lowest_volume_gain",
    "highest_sum_of_volume",
    "lowest_sum_of_volume",
    "highest_demand",
    "highest_sum_of_trade_value",
    "lowest_sum_of_trade_value",
    "highest_sum_of_trade_rap",
    "lowest_sum_of_trade_rap",
    "highest_sum_of_overall_value",
    "lowest_sum_of_overall_value",
    "closest_score_based_on_overall_value",
    "closest_score_based_on_rap",
    "highest_rap_gain",
    "lowest_rap_gain",
    "highest_algo_gain",
    "lowest_algo_gain",
    "highest_overall_gain",
    "lowest_overall_gain",
    "highest_value_gain",
    "lowest_value_gain",
    "upgrade",
    "downgrade",
)
DEFAULT_SELECT_TRADE = "lowest_rap_gain"


def items_first(keys, inventory, item_ids):
    """keys with the ones whose item is in item_ids moved to the front."""
    item_ids = set(item_ids)
    return sorted(keys, key=lambda key: inventory[key]["item_id"] not in item_ids)


def changed_items(side, inventory, item_ids) -> int:
    """How many items were added to or removed from item_ids to get side."""
    now = Counter(inventory[key]["item_id"] for key in side)
    before = Counter(item_ids)
    return sum(((now - before) + (before - now)).values())


# validate_trade's reasons, as people read them
REASON_NAMES = {
    "value_gain": "Value gain",
    "overall_gain": "Overall Value gain",
    "rap_gain": "RAP gain",
    "algo_gain": "RAP Algorithm gain",
    "min_value_of_trade": "Value sum of trade",
    "min_rap_of_trade": "RAP sum of trade",
    "close_perc": "score %",
    "overall_close_percentage": "Overall Value score %",
    "rap_close_percentage": "RAP score %",
}


def reason_text(reason) -> str:
    """'overall_gain' -> 'Overall Value gain' (anything else is left as is)."""
    return REASON_NAMES.get(reason, str(reason))


def gain_text(gain) -> str:
    """A config gain: None -> off, 0.1 -> 10%, 450 -> 450."""
    if gain is None or isinstance(gain, str):
        return "off"
    if -1 < gain < 1 and gain != 0:
        return f"{gain * 100:g}%"
    return f"{gain:,g}"


def failed_text(invalid_reasons: dict) -> str:
    """How many trades each setting stopped, biggest first."""
    failed = sorted(((n, r) for r, n in invalid_reasons.items() if n), reverse=True)
    if not failed:
        return "Nothing to try with these items."
    return "Stopped by: " + ", ".join(f"{reason_text(r)} ({n:,})" for n, r in failed)


def failed_field(invalid_reasons: dict) -> str:
    """A Discord field: how many tries each setting stopped, as a lined-up list."""
    failed = sorted(((n, r) for r, n in invalid_reasons.items() if n), reverse=True)
    if not failed:
        return "No trades to try with these items (item limits or filters)."
    width = max(len(reason_text(r)) for _, r in failed)
    lines = [f"{reason_text(r):<{width}}  {n:>9,}" for n, r in failed]
    total = sum(n for n, _ in failed)
    return (
        f"Tried {total:,} trades. What stopped them:\n```\n"
        + "\n".join(lines)
        + "\n```"
    )


def gains_table(trade: dict, maker, failed_reason=None) -> str:
    """
    Every gain of a trade next to what the config needs, as an indented table.
    Robux counts toward every gain but Value, like when trades are checked.
    """
    robux = (trade.get("their_robux") or 0) - (trade.get("self_robux") or 0)
    rows = [
        ("overall_gain", "Overall Value",
         trade["their_overall_value"] - trade["self_overall_value"] + robux,
         maker.min_overall_gain, maker.max_overall_gain),
        ("value_gain", "Value", trade["their_value"] - trade["self_value"],
         maker.min_value_gain, maker.max_value_gain),
        ("rap_gain", "RAP", trade["their_rap"] - trade["self_rap"] + robux,
         maker.min_rap_gain, maker.max_rap_gain),
        ("algo_gain", "RAP Algorithm",
         trade["their_rap_algo"] - trade["self_rap_algo"] + robux,
         maker.min_algo_gain, maker.max_algo_gain),
    ]
    lines = [f"  {'Gain':<16}{'Now':>10}   {'Min':>8}   {'Max':>8}"]
    for reason, name, gain, low, high in rows:
        mark = "   <- failed" if reason == failed_reason else ""
        lines.append(
            f"  {name:<16}{round(gain):>+10,}   {gain_text(low):>8}   "
            f"{gain_text(high):>8}{mark}"
        )
    if robux:
        lines.append(f"  (Robux in the trade: {robux:+,})")
    return "\n".join(lines)


class TradeMaker:
    def __init__(
        self,
        config=ConfigHandler("config.cfg"),
        is_outbound_checker=False,
        is_inbound_checker=False,
        gains=None,
    ):
        """gains: trading keys that replace the config's (the inbound gains)."""
        self.config = config
        trading = {**self.config.trading, **(gains or {})}

        self.min_rap_gain = trading["Minimum_RAP_Gain"]
        self.max_rap_gain = trading["Maximum_RAP_Gain"]

        self.min_overall_gain = trading["Minimum_Overall_Gain"]
        self.max_overall_gain = trading["Maximum_Overall_Gain"]

        self.min_algo_gain = trading["Minimum_Algo_Gain"]
        self.max_algo_gain = trading["Maximum_Algo_Gain"]

        # print(self.min_rap_gain, self.max_rap_gain, "hay")
        self.min_value_gain = trading["Minimum_Value_Gain"]
        self.max_value_gain = trading["Maximum_Value_Gain"]

        self.min_rap_score_percentage = self.config.trading["MinRAPScorePercentage"]
        self.max_rap_score_percentage = self.config.trading["MaxRAPScorePercentage"]

        self.min_overall_score_percentage = trading[
            "MinOverallValueScorePercentage"
        ]
        self.max_overall_score_percentage = trading[
            "MaxOverallValueScorePercentage"
        ]

        self.min_items_self = trading["MinimumItemsYourSide"]
        self.max_items_self = trading["MaximumItemsYourSide"]

        self.min_items_their = trading["MinimumItemsTheirSide"]
        self.max_items_their = trading["MaximumItemsTheirSide"]
        self.select_by = self.config.filter_generated["Select_Trade_Using"]
        self.outbound_variety = self.config.filter_generated.get("Outbound_Variety")

        self.max_robux = trading["MaxRobux"]
        self.robux_divide = trading["RobuxDividePercentage"]
        self.trade_robux = trading["TradeRobux"]

        self.min_value_of_trade = trading["MinimumValueOfTrade"]
        self.min_rap_of_trade = trading["MinimumRapOfTrade"]

        self.max_valid_trades = self.config.filter_generated["Max_Valid_Trades"]
        self.trade_timeout = self.config.filter_generated[
            "Max_Seconds_Spent_on_Generating_Trades"
        ]

        self.debug_print = self.config.debug["trading_debug"]

        self.outbound_cancel_offset = trading["Outbound_Cancel_Offset"]
        self.algo_outbound_offset = trading["Algo_Cancel_Offset"]
        if is_outbound_checker:
            if self.min_rap_gain is not None:
                self.min_rap_gain = (
                    max(0, self.min_rap_gain - self.outbound_cancel_offset)
                    if self.min_rap_gain >= 0
                    else self.min_rap_gain - self.outbound_cancel_offset
                )

            if self.min_overall_gain is not None:
                self.min_overall_gain = (
                    max(0, self.min_overall_gain - self.outbound_cancel_offset)
                    if self.min_overall_gain >= 0
                    else self.min_overall_gain - self.outbound_cancel_offset
                )

            if self.min_algo_gain is not None:
                self.min_algo_gain = (
                    max(0, self.min_algo_gain - self.algo_outbound_offset)
                    if self.min_algo_gain >= 0
                    else self.min_algo_gain - self.algo_outbound_offset
                )

            log(
                "[OUTBOUND] Cancelling sent trades that drop below: overall gain "
                f"{gain_text(self.min_overall_gain)}, RAP Algorithm gain "
                f"{gain_text(self.min_algo_gain)}, RAP gain {gain_text(self.min_rap_gain)}",
                dontPrint=True,
            )

            self.max_rap_gain = None
            self.max_algo_gain = None
            self.max_value_gain = None
            self.max_overall_gain = None

            self.min_rap_score_percentage = None
            self.max_rap_score_percentage = None

            self.min_overall_score_percentage = None
            self.max_overall_score_percentage = None

        if is_inbound_checker:
            # Judging a trade someone sent us: the minimums still apply, but the
            # maximums only exist to make our own offers look fair, so a bigger
            # win than we'd ever ask for is still worth accepting.
            self.max_rap_gain = None
            self.max_algo_gain = None
            self.max_value_gain = None
            self.max_overall_gain = None
            self.max_rap_score_percentage = None
            self.max_overall_score_percentage = None

    def select_trade(self, valid_trades, select_by="lowest_rap_gain"):
        """
        Returns the trade that matches the sort arg
        """

        select_by = select_by.lower()
        if select_by == "lowest_demand":
            return min(valid_trades, key=lambda trade: trade["demand"])

        elif select_by == "random":
            return random.choice(valid_trades)

        elif select_by == "highest_volume_gain":
            return max(
                valid_trades,
                key=lambda trade: trade["their_volume"] - trade["self_volume"],
            )

        elif select_by == "lowest_volume_gain":
            return min(
                valid_trades,
                key=lambda trade: trade["their_volume"] - trade["self_volume"],
            )

        elif select_by == "highest_sum_of_volume":
            return max(valid_trades, key=lambda trade: trade["total_volume"])

        elif select_by == "lowest_sum_of_volume":
            return min(valid_trades, key=lambda trade: trade["total_volume"])

        elif select_by == "highest_demand":
            return max(valid_trades, key=lambda trade: trade["demand"])

        elif select_by == "highest_sum_of_trade_value":
            return max(valid_trades, key=lambda trade: trade["total_value"])

        elif select_by == "lowest_sum_of_trade_value":
            return min(valid_trades, key=lambda trade: trade["total_value"])

        elif select_by == "highest_sum_of_trade_rap":
            return max(valid_trades, key=lambda trade: trade["total_rap"])

        elif select_by == "lowest_sum_of_trade_rap":
            return min(valid_trades, key=lambda trade: trade["total_rap"])

        elif select_by == "highest_sum_of_overall_value":
            return max(valid_trades, key=lambda trade: trade["total_overall_value"])

        elif select_by == "lowest_sum_of_overall_value":
            return min(valid_trades, key=lambda trade: trade["total_overall_value"])

        elif select_by == "closest_score_based_on_overall_value":
            return min(
                valid_trades, key=lambda trade: abs(trade["overall_close_score"])
            )

        elif select_by == "closest_score_based_on_rap":
            return min(valid_trades, key=lambda trade: abs(trade["rap_close_score"]))

        elif select_by == "highest_rap_gain":
            return max(
                valid_trades, key=lambda trade: trade["their_rap"] - trade["self_rap"]
            )

        elif select_by == "lowest_rap_gain":
            return min(
                valid_trades, key=lambda trade: trade["their_rap"] - trade["self_rap"]
            )

        elif select_by == "highest_algo_gain":
            return max(
                valid_trades,
                key=lambda trade: trade["their_rap_algo"] - trade["self_rap_algo"],
            )

        elif select_by == "lowest_algo_gain":
            return min(
                valid_trades,
                key=lambda trade: trade["their_rap_algo"] - trade["self_rap_algo"],
            )

        elif select_by == "highest_overall_gain":
            return max(
                valid_trades,
                key=lambda trade: (
                    trade["their_overall_value"] - trade["self_overall_value"]
                ),
            )

        elif select_by == "lowest_overall_gain":
            return min(
                valid_trades,
                key=lambda trade: (
                    trade["their_overall_value"] - trade["self_overall_value"]
                ),
            )

        elif select_by == "highest_value_gain":
            return max(
                valid_trades,
                key=lambda trade: trade["their_value"] - trade["self_value"],
            )

        elif select_by == "lowest_value_gain":
            # Filter trades where the gain is not zero
            non_zero_trades = [
                trade
                for trade in valid_trades
                if trade["self_value"] != 0 or trade["their_value"] != 0
            ]

            # for trade in valid_trades:
            #     gain = trade["their_value"] - trade["self_value"]

            if non_zero_trades:
                return min(
                    non_zero_trades,
                    key=lambda trade: trade["their_value"] - trade["self_value"],
                )
            else:
                return min(
                    valid_trades,
                    key=lambda trade: trade["their_value"] - trade["self_value"],
                )
        elif select_by == "upgrade":
            # Select the trade with the most "upgrade" (i.e., their side has more items than self side)
            return max(
                valid_trades,
                key=lambda trade: trade["num_items_their"] - trade["num_items_self"],
            )

        elif select_by == "downgrade":
            # Select the trade with the most "downgrade" (i.e., self side has more items than their side)
            return max(
                valid_trades,
                key=lambda trade: trade["num_items_self"] - trade["num_items_their"],
            )
        else:
            raise ValueError(f"Unknown selection type: {select_by}")

    def prefer_unoffered(self, valid_trades, offered):
        """
        [Filtering Generated Trades] Outbound Variety. offered = how many open
        outbounds each of our items (by instance id) is already in. Drops the
        trades whose items are offered the most, so outbounds don't all use the
        same items (once one is accepted, the rest become invalid).
        0 keeps every trade, 1 keeps only the trades using the least-offered items.
        """
        variety = getattr(self, "outbound_variety", None)
        if not variety or not offered or not valid_trades:
            return valid_trades
        reuse = [
            sum(offered.get(uaid, 0) for uaid in trade["self_side"])
            for trade in valid_trades
        ]
        low, high = min(reuse), max(reuse)
        limit = high - variety * (high - low) + 1e-9
        return [trade for trade, r in zip(valid_trades, reuse) if r <= limit]

    def generate_trade(
        self,
        self_inventory,
        their_inventory,
        counter_trade=False,
        offered=None,
        original=None,
    ):
        """
        Algorithm responsible for generating combinations and validating them..
        if its a counter trade it will select random trade to send back.
        offered: our items' open-outbound counts, for Outbound Variety.
        original: for a counter, the trade they sent, as item ids
        {"self": [...], "their": [...]}. Its items are tried first and the
        counter that changes the fewest items wins.
        """
        valid_trades = []
        self.last_failed = {}

        def pick_trade():
            # A counter stays close to their trade, so skip Outbound Variety
            candidates = (
                valid_trades
                if original
                else self.prefer_unoffered(valid_trades, offered)
            )
            if original:
                fewest = min(t["changes"] for t in candidates)
                candidates = [t for t in candidates if t["changes"] == fewest]
            # pick random trade to avoid sending the same counter trade
            if counter_trade:
                trade = self.select_trade(candidates, select_by="random")
                return trade

            select_by = (self.select_by or DEFAULT_SELECT_TRADE).lower()
            if select_by not in SELECT_TRADE_OPTIONS:
                log(
                    f"[CONFIG] Select Trade Using = {select_by} isn't a valid option, "
                    f"using {DEFAULT_SELECT_TRADE}",
                    severityNum=2,
                )
                select_by = DEFAULT_SELECT_TRADE
            return self.select_trade(candidates, select_by=select_by)

        start_time = time.perf_counter()  # Use perf_counter for better precision

        if self.debug_print:
            log("trade algorithm: getting keys", severityNum=5)

        if not self_inventory or not their_inventory:
            log(
                "[Debug] in generating trade invalid inventory, returning None",
                severityNum=5,
            )
            return None

        self_keys = list(self_inventory.keys())
        their_keys = list(their_inventory.keys())
        if original:
            # Their trade's items first, so close counters are found before a timeout
            self_keys = items_first(self_keys, self_inventory, original["self"])
            their_keys = items_first(their_keys, their_inventory, original["their"])
        if self.debug_print:
            log("Trade algorithm got keys", severityNum=5)

        # Each item's numbers, looked up once (a missing field is logged once,
        # not once per combination it's in)
        def item_totals(inventory):
            totals = {}
            for key, item in inventory.items():

                def get_value(field):
                    if item.get(field) is not None:
                        return item[field]
                    log(f"[TRADING] {item.get('item_id', key)} has no {field}, counting it as 0", dontPrint=True)
                    return 0

                totals[key] = (
                    get_value("value"),
                    get_value("rap"),
                    get_value("rap_algorithm"),
                    item["demand"] or 0,
                    get_value("total_value"),
                    get_value("item_volume"),
                )
            return totals

        self_item_totals = item_totals(self_inventory)
        their_item_totals = item_totals(their_inventory)

        def get_total_values(items, totals):
            """
            Sums value, rap, rap algorithm, demand, total value and volume of a
            combination, in the same order as the items.
            """
            value = rap = rap_algorithm = demand = total_value = volume = 0
            for key in items:
                v, r, ra, d, tv, vol = totals[key]
                value += v
                rap += r
                rap_algorithm += ra
                demand += d
                total_value += tv
                volume += vol
            return value, rap, rap_algorithm, demand, total_value, volume

        def their_combinations():
            """Their side's combinations with ids and totals, worked out once."""
            for their_side in self.generate_combinations(
                their_keys, self.min_items_their, self.max_items_their
            ):
                yield (
                    their_side,
                    {their_inventory[key]["item_id"] for key in their_side},
                    get_total_values(their_side, their_item_totals),
                )

        # Reused for every combination of our side instead of rebuilt each time
        # (capped so a huge inventory can't use too much memory)
        their_count = sum(
            math.comb(len(their_keys), r)
            for r in range(
                max(1, self.min_items_their),
                min(self.max_items_their, len(their_keys)) + 1,
            )
        )
        their_cached = (
            list(their_combinations())
            if their_count <= MAX_CACHED_COMBINATIONS
            else None
        )

        if self.debug_print:
            log("Trade algorithm: starting trade generation", severityNum=5)

        # How many tries each setting stopped, read by the declined webhook
        self.last_failed = invalid_reasons = {
            "value_gain": 0,
            "min_rap_of_trade": 0,
            "min_value_of_trade": 0,
            "close_perc": 0,
            "rap_gain": 0,
            "algo_gain": 0,
            "overall_gain": 0,
            "overall_close_percentage": 0,
            "rap_close_percentage": 0,
        }

        for self_side in self.generate_combinations(
            self_keys, self.min_items_self, self.max_items_self
        ):
            if (
                self.trade_timeout
                and time.perf_counter() - start_time > self.trade_timeout
            ):
                log(
                    "[TRADING] Ran out of time looking for a trade. "
                    + failed_text(invalid_reasons)
                )
                break
            self_side_item_ids = {self_inventory[key]["item_id"] for key in self_side}
            (
                self_value,
                self_rap,
                self_rap_algo,
                self_demand,
                self_overall_value,
                self_volume,
            ) = get_total_values(self_side, self_item_totals)

            for their_side, their_side_item_ids, their_totals in (
                their_cached if their_cached is not None else their_combinations()
            ):
                if len(self_side) == 1 and len(their_side) == 1:
                    continue
                if (
                    self.trade_timeout
                    and time.perf_counter() - start_time > self.trade_timeout
                ):
                    break

                # Ensure no overlapping item IDs
                if self_side_item_ids.isdisjoint(their_side_item_ids):
                    (
                        their_value,
                        their_rap,
                        their_rap_algo,
                        their_demand,
                        their_overall_value,
                        their_volume,
                    ) = their_totals

                    # fast continue
                    # max_possible_gain = max((x for x in pre_checks if x is not None), default=-999999999)
                    # min_possible_loss = min((x for x in pre_checks if x is not None), default=-999999999)
                    # total_value_difference = abs(self_overall_value - their_overall_value)
                    # if total_value_difference > max_possible_gain + abs(min_possible_loss):
                    #    #print(self_total_value - their_total_value, "obviously not good")
                    #     continue  # Skip this trade
                    #
                    # print(self_rap_algo, their_rap_algo, "gr")
                    send_robux = 0

                    # calc_robux = round((their_rap - self_rap) // float(2))
                    # round down
                    # NOTE: i tried to calcuate with algo but it didnt go too well
                    # Cap the result at self_rap * 0.5 (Roblox limit)
                    robux_limit = self_rap * 0.5

                    # Calculate the robux
                    calc_robux = math.floor(
                        min((their_rap - self_rap) / 4, robux_limit)
                    )

                    if calc_robux > 0 and self.trade_robux:
                        # If calculated robux if more than max robux just use max robux?
                        if calc_robux > self.max_robux:
                            calc_robux = self.max_robux

                        send_robux = calc_robux

                    validate_trade, reason = self.validate_trade(
                        self_rap=self_rap,
                        self_rap_algo=self_rap_algo,
                        self_value=self_value,
                        self_overall_value=self_overall_value,
                        their_rap=their_rap,
                        their_rap_algo=their_rap_algo,
                        their_value=their_value,
                        their_overall_value=their_overall_value,
                        robux=send_robux,
                    )
                    if validate_trade:
                        if self.debug_print:
                            log(
                                f"[DEBUG] Trade algorithm: validated trade {len(valid_trades)}",
                                severityNum=5,
                            )

                        # Calculate the trade sum (RAP and value)
                        total_value = self_value + their_value
                        total_rap = self_rap + their_rap
                        total_overall_value = self_overall_value + their_overall_value
                        total_volume = self_volume + their_volume

                        # Calculate close score (percentage)
                        rap_close_percentage = self.close_percentage(
                            self_value=self_rap, their_value=their_rap
                        )
                        overall_close_percentage = self.close_percentage(
                            self_value=self_overall_value,
                            their_value=their_overall_value,
                        )

                        # Demand is all the int of rolimons assigned demands combined
                        demand = self_demand + their_demand

                        # Determine upgrade/downgrade based on number of items
                        num_items_self = len(self_side)
                        num_items_their = len(their_side)

                        # Upgrade: Maximize number of items on their side, minimize on self side
                        upgrade = num_items_their > num_items_self

                        # Downgrade: Maximize number of items on self side, minimize on their side
                        downgrade = num_items_self > num_items_their

                        # Append all necessary details to valid_trades
                        valid_trades.append(
                            {
                                # NOTE: total = Sum of trade
                                "self_side": self_side,
                                "self_side_item_ids": self_side_item_ids,
                                "self_robux": send_robux,
                                "their_side": their_side,
                                "their_side_item_ids": their_side_item_ids,
                                "self_value": self_value,
                                "their_value": their_value,
                                "self_rap": self_rap,
                                "their_rap": their_rap,
                                "self_rap_algo": self_rap_algo,
                                "their_rap_algo": their_rap_algo,
                                "self_volume": self_volume,
                                "their_volume": their_volume,
                                "total_value": total_value,
                                "total_rap": total_rap,
                                "total_overall_value": total_overall_value,
                                "total_volume": total_volume,
                                "rap_close_score": rap_close_percentage,
                                "overall_close_score": overall_close_percentage,
                                "demand": demand,
                                "upgrade": upgrade,
                                "downgrade": downgrade,
                                "num_items_self": num_items_self,
                                "num_items_their": num_items_their,
                                "self_overall_value": self_overall_value,
                                "their_overall_value": their_overall_value,
                                "changes": (
                                    changed_items(
                                        self_side, self_inventory, original["self"]
                                    )
                                    + changed_items(
                                        their_side, their_inventory, original["their"]
                                    )
                                    if original
                                    else 0
                                ),
                            }
                        )

                        if (
                            self.max_valid_trades
                            and len(valid_trades) > self.max_valid_trades
                        ):
                            log("[TRADING] Hit Max Valid Trades, picking from those", dontPrint=True)
                            return pick_trade()

                    else:
                        # print("Not valid", self_side_item_ids, "for", their_side_item_ids)
                        if reason in invalid_reasons:
                            invalid_reasons[reason] += 1

        if valid_trades:
            return pick_trade()

        log(
            "[TRADING] No trade passed your config. " + failed_text(invalid_reasons)
        )
        return None

    def check_rap_gain(self, their_rap, self_rap):
        return self.config.check_gain(
            their_rap, self_rap, self.min_rap_gain, self.max_rap_gain
        )

    def check_value_gain(self, their_value, self_value):
        return self.config.check_gain(
            their_value, self_value, self.min_value_gain, self.max_value_gain
        )

    def check_algo_gain(self, their_algo, self_algo):
        return self.config.check_gain(
            their_algo, self_algo, self.min_algo_gain, self.max_algo_gain
        )

    def check_overall_gain(self, their_overall, self_overall):
        return self.config.check_gain(
            their_overall, self_overall, self.min_overall_gain, self.max_overall_gain
        )

    def close_percentage(self, self_value, their_value):
        # Calculate value gain and close percentage
        if self_value + their_value == 0 or their_value - self_value == 0:
            close_percentage = 0  # Prevent division by zero
        else:
            close_percentage = (
                (their_value - self_value) / (their_value + self_value)
            ) * 100

        return close_percentage

    def validate_trade(
        self,
        self_rap,
        self_rap_algo,
        self_value,
        their_rap,
        their_rap_algo,
        their_value,
        self_overall_value,
        their_overall_value,
        robux=None,
        their_robux=None,
    ):
        """
        robux / their_robux: Robux each side adds. They count at face value
        toward RAP, Overall Value and RAP Algorithm (not Value, which is
        Rolimons values only), and toward the score percentages.
        """
        if robux:
            self_rap += robux
            self_overall_value += robux
            self_rap_algo += robux
        if their_robux:
            their_rap += their_robux
            their_overall_value += their_robux
            their_rap_algo += their_robux
        if (
            self.min_value_of_trade
            and self.min_value_of_trade > self_value + their_value
        ):
            # print("sum of trade", self_value, their_value)
            return False, "min_value_of_trade"

        if self.min_rap_of_trade and self.min_rap_of_trade > self_rap + their_rap:
            return False, "min_rap_of_trade"

        # Precompute the total value and RAP for both sides in a single loop
        # Calculate value gain and close percentage
        rap_close_percentage = self.close_percentage(
            self_value=self_rap, their_value=their_rap
        )
        overall_close_percentage = self.close_percentage(
            self_value=self_overall_value, their_value=their_overall_value
        )
        # Check if close percentage is within the acceptable range
        if (
            self.min_overall_score_percentage
            and overall_close_percentage < self.min_overall_score_percentage
            or self.max_overall_score_percentage
            and overall_close_percentage > self.max_overall_score_percentage
        ):
            return False, "overall_close_percentage"

        if (
            self.min_rap_score_percentage
            and rap_close_percentage < self.min_rap_score_percentage
            or self.max_rap_score_percentage
            and rap_close_percentage > self.max_rap_score_percentage
        ):
            return False, "rap_close_percentage"

        if not self.check_overall_gain(their_overall_value, self_overall_value):
            return False, "overall_gain"
        # Check if RAP gain passes the criteria
        if not self.check_rap_gain(their_rap, self_rap):
            # print("rap gain false their, self", their_rap, self_rap)
            return False, "rap_gain"

        if not self.check_algo_gain(their_rap_algo, self_rap_algo):
            # print("algo gain false their, self", their_rap_algo, self_rap_algo)
            return False, "algo_gain"

        # Check if value gain passes the criteria
        if not self.check_value_gain(their_value, self_value):
            # print("valu gain false their, self", their_value, self_value)
            return False, "value_gain"

        # print("trade valid")
        return True, None

    def generate_combinations(self, keys, min_items=1, max_items=4):
        """
        Lazily generates combinations of a list of keys to save memory.
        Uses a generator to yield combinations one at a time.
        """
        if not keys:
            log("[TRADING] No items to make trades from", dontPrint=True)
            return
            # Returning an empty generator

        if len(keys) < min_items:
            log(
                f"[TRADING] Only {len(keys)} item(s), but a side needs at least {min_items}", dontPrint=True)
            log("[TRADING] Not sending trades with these items", dontPrint=True)
            # return

        # Adjust bounds for min_items and max_items
        min_items = max(1, min_items)
        max_items = min(max_items, len(keys))

        # Lazily generate combinations for each size
        for r in range(min_items, max_items + 1):
            for combination in combinations(keys, r):
                yield combination  # Yield one combination at a time
