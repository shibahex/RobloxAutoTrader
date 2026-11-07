import functools
from collections import Counter
from handler.counter_history import trade_signature
from handler.handle_config import ConfigHandler, _convert_gain
from itertools import combinations
import math
import random
import time
from handler.handle_logs import log, terminal_width


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
# A reason ending in "_max" failed the setting's maximum, otherwise its minimum.
REASON_NAMES = {
    "value_gain": "Value gain (below min)",
    "value_gain_max": "Value gain (above max)",
    "overall_gain": "Overall Value gain (below min)",
    "overall_gain_max": "Overall Value gain (above max)",
    "rap_gain": "RAP gain (below min)",
    "rap_gain_max": "RAP gain (above max)",
    "algo_gain": "RAP Algorithm gain (below min)",
    "algo_gain_max": "RAP Algorithm gain (above max)",
    "min_value_of_trade": "Value sum of trade (below min)",
    "min_rap_of_trade": "RAP sum of trade (below min)",
    "overall_close_percentage": "Overall Value score % (below min)",
    "overall_close_percentage_max": "Overall Value score % (above max)",
    "rap_close_percentage": "RAP score % (below min)",
    "rap_close_percentage_max": "RAP score % (above max)",
    "already_sent": "Already sent to them",
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


@functools.lru_cache(maxsize=256)
def gain_bounds(min_gain, max_gain) -> tuple:
    """
    A gain setting pair as (low, low is %, high, high is %), worked out once.
    Same rules as ConfigHandler.check_gain: -1 to 1 is a percentage.
    """

    def bound(gain):
        if gain is None:
            return None, False
        number, is_percentage = _convert_gain(gain)
        return (number * 100 if is_percentage else number), is_percentage

    return (*bound(min_gain), *bound(max_gain))


BELOW_MIN, ABOVE_MAX = 1, 2


def gain_miss(gain, base, bounds) -> int:
    """
    ConfigHandler.check_gain on bounds from gain_bounds, without the setup:
    0 = passes, BELOW_MIN or ABOVE_MAX.
    """
    low, low_percentage, high, high_percentage = bounds
    if low is not None:
        profit = (gain / base * 100 if base else 0) if low_percentage else gain
        if profit < low:
            return BELOW_MIN
    if high is not None:
        profit = (gain / base * 100 if base else 0) if high_percentage else gain
        if profit > high:
            return ABOVE_MAX
    return 0


def gain_in_range(gain, base, bounds) -> bool:
    return not gain_miss(gain, base, bounds)


def failed_stats(failed) -> dict:
    """
    {"tried": n, "failed": {reason: n}, "only": {reason: n}} from
    TradeMaker.last_failed. A plain {reason: n} counts as failed only.
    """
    if failed and "failed" in failed:
        return failed
    counts = {r: n for r, n in (failed or {}).items() if r != "already_sent"}
    return {"tried": sum(counts.values()), "failed": counts, "only": {}}


def failed_rows(failed) -> list:
    """(setting, failed, only) for every setting, the most useful first."""
    stats = failed_stats(failed)
    only = stats["only"]
    rows = [(reason_text(r), n, only.get(r, 0)) for r, n in stats["failed"].items()]
    return sorted(rows, key=lambda row: (-row[2], -row[1]))


def failed_summary(failed) -> str:
    """'Tried 5,096 trades, none passed.' plus which setting to loosen, if one."""
    stats = failed_stats(failed)
    passed = stats.get("passed", 0)
    tried = stats["tried"]
    text = (
        f"Tried {tried:,} trade{'' if tried == 1 else 's'}, "
        f"{f'{passed:,}' if passed else 'none'} passed."
    )
    rows = failed_rows(stats)
    if rows and rows[0][2]:
        name, _, only = rows[0]
        text += f"\nLoosening only {name} would let {only:,} pass."
    elif stats["only"] and stats["tried"] > passed:
        text += "\nEvery trade failed 2+ settings, so no single one blocks them."
    already = (failed or {}).get("already_sent")
    if already:
        text += f"\n{already:,} that passed were already sent to them."
    return text


def failed_table(failed, columns=1) -> list:
    """The rows as lined-up text: setting, how many failed it, how many failed only it."""
    rows = failed_rows(failed)
    name_width = max([len("Setting")] + [len(name) for name, _, _ in rows])
    number_width = max([6] + [len(f"{n:,}") for _, n, _ in rows])
    show_only = bool(failed_stats(failed)["only"])

    def cell(name, n, only):
        text = f"{name:<{name_width}}  {n:>{number_width}}"
        return text + (f"  {only:>12}" if show_only else "")

    head = cell("Setting", "Failed", "Sole Failure")
    cells = [cell(name, f"{n:,}", f"{only:,}") for name, n, only in rows]
    if columns == 2 and len(cells) > 1:
        half = (len(cells) + 1) // 2
        lefts, rights = cells[:half], cells[half:] + [""]
        return [f"{head} | {head}"] + [
            left + (" | " + right if right else "") for left, right in zip(lefts, rights)
        ]
    return [head] + cells


ONLY_NOTE = "Sole Failure = trades that failed only that limit, so they pass without it."


def failed_text(failed, width=None) -> str:
    """
    For the console: the summary, then a table of every setting with how many
    trades failed it, one setting per line. width is unused (kept for callers).
    """
    stats = failed_stats(failed)
    if not stats["tried"]:
        return "There were no trades to try with these items."
    lines = [failed_summary(stats)] + failed_table(stats)
    if stats["only"]:
        lines.append(ONLY_NOTE)
    return "\n".join(lines)


def failed_field(failed) -> str:
    """A Discord field: the summary, then the table in a code block."""
    stats = failed_stats(failed)
    if not stats["tried"]:
        return "No trades to try with these items (item limits or filters)."
    note = f"\n{ONLY_NOTE}" if stats["only"] else ""
    return (
        failed_summary(stats)
        + "\n```\n"
        + "\n".join(failed_table(stats))
        + "\n```"
        + note
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
    lines = [f"{'Gain':<16}{'Now':>9}  {'Min':>7}  {'Max':>7}"]
    for reason, name, gain, low, high in rows:
        failed = str(failed_reason or "").removesuffix("_max")
        mark = "  <- failed" if reason == failed else ""
        lines.append(
            f"{name:<16}{round(gain):>+9,}  {gain_text(low):>7}  "
            f"{gain_text(high):>7}{mark}"
        )
    if robux:
        lines.append(f"(Robux in the trade: {robux:+,})")
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

        self.min_rap_score_percentage = trading["MinRAPScorePercentage"]
        self.max_rap_score_percentage = trading["MaxRAPScorePercentage"]

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
        avoid=None,
        about="",
    ):
        """
        Algorithm responsible for generating combinations and validating them..
        if its a counter trade it will select random trade to send back.
        offered: our items' open-outbound counts, for Outbound Variety.
        original: for a counter, the trade they sent, as item ids
        {"self": [...], "their": [...]}. Its items are tried first and the
        counter that changes the fewest items wins.
        avoid: signatures (trade_signature) of trades not to send again, like
        counters this trader already got.
        about: who the trade is for, in the "no trade passed" message. Counters
        don't log it (the inbound handler explains the decline instead).
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
            if avoid:
                fresh = [t for t in candidates if signature(t) not in avoid]
                self.last_failed["already_sent"] = len(candidates) - len(fresh)
                candidates = fresh
                if not candidates:
                    return None
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

        def signature(trade):
            return trade_signature(
                [self_inventory[key]["item_id"] for key in trade["self_side"]],
                [their_inventory[key]["item_id"] for key in trade["their_side"]],
                trade["self_robux"],
            )

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

        # How many tries failed each setting, and how many failed only that
        # one (they'd pass with it off). Read by the "no trade passed" messages.
        reasons = (
            "value_gain", "min_rap_of_trade", "min_value_of_trade", "rap_gain",
            "algo_gain", "overall_gain",
            "overall_close_percentage", "rap_close_percentage",
        )
        maximums = {
            "overall_gain_max": self.max_overall_gain,
            "rap_gain_max": self.max_rap_gain,
            "algo_gain_max": self.max_algo_gain,
            "value_gain_max": self.max_value_gain,
            "overall_close_percentage_max": self.max_overall_score_percentage,
            "rap_close_percentage_max": self.max_rap_score_percentage,
        }
        reasons += tuple(key for key, limit in maximums.items() if limit is not None)
        invalid_reasons = dict.fromkeys(reasons, 0)
        only_reasons = dict.fromkeys(reasons, 0)
        tried = 0

        def stats():
            self.last_failed.update(
                tried=tried,
                passed=len(valid_trades),
                failed=invalid_reasons,
                only=only_reasons,
            )
            return self.last_failed

        for self_side in self.generate_combinations(
            self_keys, self.min_items_self, self.max_items_self
        ):
            if (
                self.trade_timeout
                and time.perf_counter() - start_time > self.trade_timeout
            ):
                if not counter_trade:
                    log(
                        f"[TRADING] {about}ran out of time looking for a trade.\n"
                        + failed_text(stats())
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

                    # Robux counts toward everything but Value (see validate_trade)
                    reason = self.trade_failures(
                        self_rap + send_robux,
                        self_rap_algo + send_robux,
                        self_value,
                        their_rap,
                        their_rap_algo,
                        their_value,
                        self_overall_value + send_robux,
                        their_overall_value,
                    )
                    tried += 1
                    if not reason:
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
                            stats()
                            return pick_trade()

                    else:
                        for failure in reason:
                            invalid_reasons[failure] = invalid_reasons.get(failure, 0) + 1
                        if len(reason) == 1:
                            only_reasons[reason[0]] = only_reasons.get(reason[0], 0) + 1

        stats()
        if valid_trades:
            return pick_trade()

        log(
            f"[TRADING] {about}no trade passed your config.\n"
            + failed_text(self.last_failed),
            dontPrint=counter_trade,
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
        all_failures=False,
    ):
        """
        Returns (valid, first setting it failed). all_failures: (valid, every
        setting it failed) instead, for the "what stopped them" table.
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
        failures = self.trade_failures(
            self_rap, self_rap_algo, self_value, their_rap, their_rap_algo,
            their_value, self_overall_value, their_overall_value,
            first_only=not all_failures,
        )
        if all_failures:
            return not failures, failures
        return (False, failures[0]) if failures else (True, None)

    def trade_failures(
        self,
        self_rap,
        self_rap_algo,
        self_value,
        their_rap,
        their_rap_algo,
        their_value,
        self_overall_value,
        their_overall_value,
        first_only=False,
    ) -> list:
        """
        Every setting the trade fails, in the order they're checked (Robux
        already added). first_only: stop at the first one. Runs for every
        combination, so it's written for speed.
        """
        failures = []
        if (
            self.min_value_of_trade
            and self.min_value_of_trade > self_value + their_value
        ):
            failures.append("min_value_of_trade")
            if first_only:
                return failures
        if self.min_rap_of_trade and self.min_rap_of_trade > self_rap + their_rap:
            failures.append("min_rap_of_trade")
            if first_only:
                return failures

        low, high = self.min_overall_score_percentage, self.max_overall_score_percentage
        if low or high:
            score = self.close_percentage(self_overall_value, their_overall_value)
            if low and score < low or high and score > high:
                failures.append(
                    "overall_close_percentage"
                    if low and score < low
                    else "overall_close_percentage_max"
                )
                if first_only:
                    return failures
        low, high = self.min_rap_score_percentage, self.max_rap_score_percentage
        if low or high:
            score = self.close_percentage(self_rap, their_rap)
            if low and score < low or high and score > high:
                failures.append(
                    "rap_close_percentage" if low and score < low else "rap_close_percentage_max"
                )
                if first_only:
                    return failures

        low, high = self.min_overall_gain, self.max_overall_gain
        if low is not None or high is not None:
            miss = gain_miss(
                their_overall_value - self_overall_value,
                self_overall_value,
                gain_bounds(low, high),
            )
            if miss:
                failures.append("overall_gain" if miss == BELOW_MIN else "overall_gain_max")
                if first_only:
                    return failures
        low, high = self.min_rap_gain, self.max_rap_gain
        if low is not None or high is not None:
            miss = gain_miss(their_rap - self_rap, self_rap, gain_bounds(low, high))
            if miss:
                failures.append("rap_gain" if miss == BELOW_MIN else "rap_gain_max")
                if first_only:
                    return failures
        low, high = self.min_algo_gain, self.max_algo_gain
        if low is not None or high is not None:
            miss = gain_miss(
                their_rap_algo - self_rap_algo, self_rap_algo, gain_bounds(low, high)
            )
            if miss:
                failures.append("algo_gain" if miss == BELOW_MIN else "algo_gain_max")
                if first_only:
                    return failures
        low, high = self.min_value_gain, self.max_value_gain
        if low is not None or high is not None:
            miss = gain_miss(their_value - self_value, self_value, gain_bounds(low, high))
            if miss:
                failures.append("value_gain" if miss == BELOW_MIN else "value_gain_max")
                if first_only:
                    return failures
        return failures

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
