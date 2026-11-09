import itertools
import collections
import functools
from collections import Counter
from handler.counter_history import trade_signature
from handler.handle_config import ConfigHandler, _convert_gain
from itertools import combinations
import math
import random
import time
from handler.handle_logs import log


# Their side's combinations are worked out once and reused when there are at
# most this many (about 30 items, up to 4 per side); bigger ones are made as needed
MAX_CACHED_COMBINATIONS = 300_000


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


def _gain(field):
    return lambda trade: trade[f"their_{field}"] - trade[f"self_{field}"]


def _negative(key):
    return lambda trade: -key(trade)


_rap_gain, _algo_gain = _gain("rap"), _gain("rap_algo")
_value_gain, _overall_gain, _volume_gain = _gain("value"), _gain("overall_value"), _gain("volume")

# Pick Trade By -> the number to make smallest. min() keeps the first trade on
# a tie, the same as max() would for the highest_ options.
PICK_KEYS = {
    "lowest_demand": lambda trade: trade["demand"],
    "highest_demand": lambda trade: -trade["demand"],
    "highest_volume_gain": _negative(_volume_gain),
    "lowest_volume_gain": _volume_gain,
    "highest_sum_of_volume": lambda trade: -trade["total_volume"],
    "lowest_sum_of_volume": lambda trade: trade["total_volume"],
    "highest_sum_of_trade_value": lambda trade: -trade["total_value"],
    "lowest_sum_of_trade_value": lambda trade: trade["total_value"],
    "highest_sum_of_trade_rap": lambda trade: -trade["total_rap"],
    "lowest_sum_of_trade_rap": lambda trade: trade["total_rap"],
    "highest_sum_of_overall_value": lambda trade: -trade["total_overall_value"],
    "lowest_sum_of_overall_value": lambda trade: trade["total_overall_value"],
    "closest_score_based_on_overall_value": lambda trade: abs(trade["overall_close_score"]),
    "closest_score_based_on_rap": lambda trade: abs(trade["rap_close_score"]),
    "highest_rap_gain": _negative(_rap_gain),
    "lowest_rap_gain": _rap_gain,
    "highest_algo_gain": _negative(_algo_gain),
    "lowest_algo_gain": _algo_gain,
    "highest_overall_gain": _negative(_overall_gain),
    "lowest_overall_gain": _overall_gain,
    "highest_value_gain": _negative(_value_gain),
    # Trades with a valued item first
    "lowest_value_gain": lambda trade: (
        trade["self_value"] == 0 and trade["their_value"] == 0,
        _value_gain(trade),
    ),
    # Most items on their side compared to ours
    # Upgrade: you give more items and get fewer (bigger) ones back
    "upgrade": lambda trade: trade["num_items_their"] - trade["num_items_self"],
    # Downgrade: you give fewer items and get more (smaller) ones back
    "downgrade": lambda trade: trade["num_items_self"] - trade["num_items_their"],
}


# Short names Pick Trade By also accepts
PICK_ALIASES = {}


BLEND_PREFIX = "blend:"


def is_blend(select_by) -> bool:
    """Pick Trade By = blend: a, b, c (see blend_pick)."""
    return str(select_by or "").strip().lower().startswith(BLEND_PREFIX)


def parse_pick(select_by):
    """
    Pick Trade By -> ([options], random ties). Options can be combined with
    "+": the first decides, the next breaks its ties, and so on
    ("lowest_overall_gain + highest_demand + upgrade").
    "random" anywhere = random among what's still tied.
    "blend: a, b, c" lists options for blend_pick instead (commas or +).
    Raises ValueError on an unknown option.
    """
    text = str(select_by or "").strip()
    if is_blend(text):
        text = text[len(BLEND_PREFIX):].replace(",", "+")
    names = [
        PICK_ALIASES.get(name.strip().lower(), name.strip().lower())
        for name in text.split("+")
        if name.strip()
    ]
    if not names:
        raise ValueError("Pick Trade By is empty")
    unknown = [name for name in names if name not in SELECT_TRADE_OPTIONS]
    if unknown:
        raise ValueError(f"unknown Pick Trade By option: {', '.join(unknown)}")
    random_ties = "random" in names
    return [name for name in names if name != "random"], random_ties


def pick_key(names):
    """One sort key for parsed Pick Trade By options (None = no order)."""
    if not names:
        return None
    if len(names) == 1:
        return PICK_KEYS[names[0]]
    keys = [PICK_KEYS[name] for name in names]
    return lambda trade: tuple(key(trade) for key in keys)


def blend_weights(count: int) -> list:
    """The first option counts most: 4 options -> 4, 3, 2, 1."""
    return list(range(count, 0, -1))


def blend_pick(trades: list, names: list, random_ties=False):
    """
    Pick Trade By = blend: every trade is ranked on each option (0 = best,
    1 = worst, ties share a rank), and the ranks are added up with the first
    option weighted most (blend_weights). The lowest total wins; ties go to
    the first trade found (or a random one with random in the list).
    """
    if not trades:
        return None
    if len(trades) == 1 or not names:
        return random.choice(trades) if random_ties and not names else trades[0]
    totals = [0.0] * len(trades)
    last = len(trades) - 1
    for name, weight in zip(names, blend_weights(len(names))):
        key = PICK_KEYS[name]
        values = [key(trade) for trade in trades]
        order = sorted(range(len(trades)), key=values.__getitem__)
        start = 0
        while start < len(order):
            end = start
            while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
                end += 1
            rank = (start + end) / 2 / last  # tied trades share the middle rank
            for position in range(start, end + 1):
                totals[order[position]] += weight * rank
            start = end + 1
    best = min(totals)
    tied = [i for i, total in enumerate(totals) if abs(total - best) < 1e-9]
    return trades[random.choice(tied) if random_ties else tied[0]]


# blend keeps every tied passing trade to rank them; past this many, a random
# sample of them (so memory stays bounded)
BLEND_KEEP = 5000


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


def cancel_minimum(minimum, offset):
    """
    [Outbounds] Cancel Offset: how far a sent trade's profit can drop below
    the minimum before it's cancelled. Between 0 and 1 = that share of the
    minimum (0.02 = 2% under it), otherwise Robux. It never goes below 0
    (unless the minimum is negative), so a trade that turns into a loss is
    always cancelled.
    """
    if minimum is None:
        return None
    offset = offset if isinstance(offset, (int, float)) and offset > 0 else 0
    if offset < 1:
        offset = abs(minimum) * offset
    lowered = minimum - offset
    return max(0, lowered) if minimum >= 0 else lowered


def trade_lines(header: str, fields: dict, profit) -> str:
    """The console version of a trade's webhook: header, items both ways, breakdown."""

    def items(name):
        text = fields[name][0]
        return "\n".join(map(str, text)) if isinstance(text, tuple) else text

    return "\n".join(
        [
            f"{header} ({profit:+,} overall)",
            "You give:",
            *("  " + line for line in items("Send").splitlines()),
            "You get:",
            *("  " + line for line in items("Receive").splitlines()),
            fields["Trade Breakdown"][0],
        ]
    )


def failed_stats(failed) -> dict:
    """
    {"tried": n, "failed": {reason: n}, "only": {reason: n}} from
    TradeMaker.last_failed. A plain {reason: n} counts as failed only.
    """
    if failed and "failed" in failed:
        return failed
    counts = {
        r: n for r, n in (failed or {}).items() if r not in ("already_sent", "why_none")
    }
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
    # Trades this far out of the Overall Value range weren't checked further,
    # so how many fail only that is a minimum
    # Trades ruled out early were only checked against one gain, so they
    # aren't in the Sole Failure counts
    ruled_out = stats.get("ruled_out", 0)
    if rows and rows[0][2]:
        name, _, only = rows[0]
        at_least = "at least " if ruled_out else ""
        text += f"\nLoosening only {name} would let {at_least}{only:,} pass."
    elif ruled_out:
        text += (
            f"\n{ruled_out:,} were far outside a gain's range, so only that "
            "gain was counted for them."
        )
    elif stats["only"] and stats["tried"] > passed:
        text += "\nEvery trade failed 2+ settings, so no single one blocks them."
    not_made = stats.get("not_made", 0)
    if not_made:
        text += f"\nSkipped {not_made:,} more that couldn't fit your gain ranges."
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
        why = (failed or {}).get("why_none")
        return f"There were no trades to try: {why}" if why else "There were no trades to try with these items."
    lines = [failed_summary(stats)] + failed_table(stats)
    if stats["only"]:
        lines.append(ONLY_NOTE)
    return "\n".join(lines)


def failed_field(failed) -> str:
    """A Discord field: the summary, then the table in a code block."""
    stats = failed_stats(failed)
    if not stats["tried"]:
        why = (failed or {}).get("why_none")
        return f"No trades to try: {why}" if why else "No trades to try with these items (item limits or filters)."
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
        now = "n/a" if gain is None else f"{round(gain):+,}"
        lines.append(
            f"{name:<16}{now:>9}  {gain_text(low):>7}  "
            f"{gain_text(high):>7}{mark}"
        )
    if robux:
        lines.append(f"(Robux in the trade: {robux:+,})")
    return "\n".join(lines)



class TradePicker:
    """
    Picks generate_trade's trade while the search runs. It keeps only the best
    trade for each Outbound Variety count rather than every passing trade, so
    memory stays flat however many pass, and it picks the same trade a full
    list would. Order of preference: Outbound Variety, the most of our
    projected items given away, not already sent, the
    fewest changed items (counters), then Pick Trade By (or random).
    """

    def __init__(self, select_by, variety=None, offered=None, avoid=None,
                 signature=None):
        names, self.random_ties = parse_pick(select_by)
        # blend: options ranked together at the end (blend_pick)
        self.blend = names if is_blend(select_by) else None
        self.key = None if self.blend else pick_key(names)
        self.random_ties = self.random_ties or (self.key is None and not self.blend)
        self.variety = variety if variety and offered else None
        self.offered = offered
        self.avoid = avoid
        self.signature = signature
        self.passed = 0
        self.already_sent = 0
        self.low = self.high = None
        # Outbound Variety count -> [rank, order, trade, ties]
        self.best = {}
        self.avoided = Counter()

    def add(self, trade):
        self.passed += 1
        reuse = (
            sum(self.offered.get(uaid, 0) for uaid in trade["self_side"])
            if self.variety
            else 0
        )
        if self.low is None or reuse < self.low:
            self.low = reuse
        if self.high is None or reuse > self.high:
            self.high = reuse
        if self.avoid and self.signature(trade) in self.avoid:
            self.avoided[reuse] += 1
            return
        rank = (
            -trade.get("projected_given", 0),
            trade["changes"],
            self.key(trade) if self.key else 0,
        )
        best = self.best.get(reuse)
        if self.blend:
            # Keep every trade tied on the rest; blend_pick ranks them
            if best is None or rank < best[0]:
                self.best[reuse] = [rank, self.passed, [trade], 1]
            elif rank == best[0]:
                best[3] += 1
                if len(best[2]) < BLEND_KEEP:
                    best[2].append(trade)
                else:
                    # Reservoir sample: every tied trade is equally likely kept
                    slot = random.randrange(best[3])
                    if slot < BLEND_KEEP:
                        best[2][slot] = trade
            return
        if best is None or rank < best[0]:
            self.best[reuse] = [rank, self.passed, trade, 1]
        elif rank == best[0] and self.random_ties:
            # Random among the tied trades: each is kept with chance 1/ties
            best[3] += 1
            if random.randrange(best[3]) == 0:
                best[2] = trade

    def pick(self):
        if self.low is None:
            return None
        limit = (
            self.high - self.variety * (self.high - self.low) + 1e-9
            if self.variety
            else math.inf
        )
        self.already_sent = sum(n for r, n in self.avoided.items() if r <= limit)
        kept = [best for reuse, best in self.best.items() if reuse <= limit]
        if not kept:
            return None
        top = min(best[0] for best in kept)
        tied = [best for best in kept if best[0] == top]
        if self.blend:
            trades = [trade for best in sorted(tied, key=lambda b: b[1]) for trade in best[2]]
            return blend_pick(trades, self.blend, self.random_ties)
        if not self.random_ties:
            return min(tied, key=lambda best: best[1])[2]
        return random.choices(tied, weights=[best[3] for best in tied])[0][2]


class TradeMaker:
    def __init__(
        self,
        config=None,
        is_outbound_checker=False,
        is_inbound_checker=False,
        gains=None,
    ):
        """gains: trading keys that replace the config's (the inbound gains)."""
        self.config = config if config is not None else ConfigHandler("config.cfg")
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
        # True: a trade with no valued items on either side skips Value Gain
        self.skip_value_without_valued = bool(trading.get("Skip_Value_Gain_Without_Valued"))

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
        # [Projected] Prioritize Sending Projecteds: trades that give away
        # more of our projected items win
        self.prioritize_projected = (
            getattr(self.config, "projected_detection", None) or {}
        ).get("Prioritize_Sending_Projecteds", True)
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
            overall_offset = self.outbound_cancel_offset
            self.min_rap_gain = cancel_minimum(self.min_rap_gain, overall_offset)
            self.min_overall_gain = cancel_minimum(self.min_overall_gain, overall_offset)
            self.min_algo_gain = cancel_minimum(self.min_algo_gain, self.algo_outbound_offset)

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
        """Returns the trade that Pick Trade By (select_by) prefers."""
        names, random_ties = parse_pick(select_by)
        if is_blend(select_by):
            return blend_pick(list(valid_trades), names, random_ties)
        key = pick_key(names)
        if key is None:
            return random.choice(valid_trades)
        best = min(valid_trades, key=key)
        if not random_ties:
            return best
        return random.choice([trade for trade in valid_trades if key(trade) == key(best)])

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
        self.last_failed = {}

        def signature(trade):
            return trade_signature(
                [self_inventory[key]["item_id"] for key in trade["self_side"]],
                [their_inventory[key]["item_id"] for key in trade["their_side"]],
                trade["self_robux"],
            )

        if counter_trade:
            # Random, so the same counter isn't sent every time
            select_by = "random"
        else:
            select_by = (self.select_by or DEFAULT_SELECT_TRADE).lower()
            try:
                parse_pick(select_by)
            except ValueError as e:
                log(
                    f"[CONFIG] Pick Trade By = {select_by}: {e}, "
                    f"using {DEFAULT_SELECT_TRADE}",
                    severityNum=2,
                )
                select_by = DEFAULT_SELECT_TRADE
        picker = TradePicker(
            select_by,
            # A counter stays close to their trade, so skip Outbound Variety
            variety=None if original else getattr(self, "outbound_variety", None),
            offered=offered,
            avoid=avoid,
            signature=signature,
        )

        def pick_trade():
            trade = picker.pick()
            if avoid:
                self.last_failed["already_sent"] = picker.already_sent
            return trade

        start_time = time.perf_counter()  # Use perf_counter for better precision

        if self.debug_print:
            log("trade algorithm: getting keys", severityNum=5)

        if not self_inventory or not their_inventory:
            self.last_failed = {
                "why_none": "You have no usable items."
                if not self_inventory
                else "They have no usable items (after your item filters)."
            }
            log(
                "[Debug] in generating trade invalid inventory, returning None",
                severityNum=5,
            )
            return None

        self_keys = list(self_inventory.keys())
        self_projected = (
            {key for key, item in self_inventory.items() if item.get("projected")}
            if getattr(self, "prioritize_projected", True)
            else set()
        )
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

        # One bit per item id, so "no item on both sides" is a single AND
        item_bits = {}
        for inventory in (self_inventory, their_inventory):
            for item in inventory.values():
                item_bits.setdefault(item["item_id"], 1 << len(item_bits))

        def side_mask(side, inventory):
            mask = 0
            for key in side:
                mask |= item_bits[inventory[key]["item_id"]]
            return mask

        def their_combinations():
            """
            Their side's combinations, worked out once: (side, item mask,
            totals, item count).
            """
            for their_side in self.generate_combinations(
                their_keys, self.min_items_their, self.max_items_their
            ):
                totals = get_total_values(their_side, their_item_totals)
                yield (
                    their_side,
                    side_mask(their_side, their_inventory),
                    totals,
                    len(their_side),
                )

        # Reused for every combination of our side instead of rebuilt each time
        # (capped so a huge inventory can't use too much memory)
        all_their_count = sum(
            math.comb(len(their_keys), r)
            for r in range(
                max(1, self.min_items_their),
                min(self.max_items_their, len(their_keys)) + 1,
            )
        )
        cache = {}

        def all_their_combinations():
            """Every combination of their side, cached when it fits in memory."""
            if all_their_count > MAX_CACHED_COMBINATIONS:
                return their_combinations()
            if "all" not in cache:
                cache["all"] = list(their_combinations())
            return cache["all"]

        def items_by(measure):
            """
            Their items sorted by one number (a their-totals index), with
            suffix sums for in_range_combinations. None if
            an item's number is negative (sums can't be bounded then).
            """
            if measure not in cache:
                rows = []
                for key in their_keys:
                    rows.append((their_item_totals[key][measure], key))
                rows.sort(key=lambda row: row[0])
                amounts = [amount for amount, _ in rows]
                if amounts and amounts[0] < 0:
                    cache[measure] = None
                else:
                    suffix = [0] * (len(amounts) + 1)
                    for i in range(len(amounts) - 1, -1, -1):
                        suffix[i] = suffix[i + 1] + amounts[i]
                    cache[measure] = (amounts, [key for _, key in rows], suffix)
            return cache[measure]

        def in_range_combinations(measure, lowest, highest, counted):
            """
            Exactly the combinations of their side whose total of `measure` is
            between lowest and highest, without building the others: items are
            added cheapest first, so a path that goes over highest, or can't
            reach lowest even with their biggest items, is dropped with
            everything it would lead to. counted[0] += combinations made.
            """
            amounts, keys, suffix = items_by(measure)
            # Sides list their items in inventory order, however they were found
            position = cache.setdefault("position", {k: i for i, k in enumerate(their_keys)})
            n = len(amounts)
            fewest = max(1, self.min_items_their)
            most = min(self.max_items_their, n)
            # Items worth 0 here never change the total, so the walk only goes
            # through the others ("cores") and fills spare room with these
            zeros = 0
            while zeros < n and amounts[zeros] == 0:
                zeros += 1

            def timed_out():
                return self.trade_timeout and time.perf_counter() - start_time > self.trade_timeout

            def cores():
                """
                (positions, total) of every set of non-zero items with a total
                in range, depth-first with an explicit stack.
                """
                if lowest <= 0 <= highest:
                    yield (), 0
                chosen, totals, next_try = [], [0], [zeros]
                steps = 0
                while next_try:
                    steps += 1
                    if not steps & 4095 and timed_out():
                        return
                    depth = len(chosen)
                    j, total = next_try[-1], totals[-1]
                    room = most - depth
                    while j < n and room:
                        reached = total + amounts[j]
                        if reached > highest:
                            j = n  # every item after this one is worth more
                            break
                        # This item plus the biggest that could follow still
                        # can't reach lowest: try a bigger one
                        if reached + suffix[max(j + 1, n - (room - 1))] < lowest:
                            j += 1
                            continue
                        break
                    if j >= n or not room:
                        next_try.pop()
                        if chosen:
                            chosen.pop()
                            totals.pop()
                        continue
                    next_try[-1] = j + 1
                    chosen.append(j)
                    totals.append(reached)
                    next_try.append(j + 1)
                    if reached >= lowest:
                        yield tuple(chosen), reached

            def walk():
                made = 0
                for core, _ in cores():
                    for extra in range(max(0, fewest - len(core)), most - len(core) + 1):
                        for filler in itertools.combinations(range(zeros), extra):
                            made += 1
                            if not made & 4095 and timed_out():
                                return
                            side = tuple(
                                sorted((keys[i] for i in core + filler), key=position.__getitem__)
                            )
                            if not side:
                                continue
                            counted[0] += 1
                            yield (
                                side,
                                side_mask(side, their_inventory),
                                get_total_values(side, their_item_totals),
                                len(side),
                            )

            return walk()

        def combinations_for(windows, counted):
            """
            Their combinations worth checking against one of our sides: the
            ones inside the narrowest gain range, else all of them.
            """
            best = None
            for index, lowest, highest, reason in windows:
                if highest == math.inf:
                    continue
                if items_by(index) is None:
                    continue
                width = highest - max(lowest, 0)
                if best is None or width < best[0]:
                    best = (width, index, lowest, highest, reason)
            if best is None:
                return all_their_combinations(), None
            _, index, lowest, highest, reason = best
            return in_range_combinations(index, lowest, highest, counted), reason

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
        invalid_reasons = collections.defaultdict(int, dict.fromkeys(reasons, 0))
        only_reasons = collections.defaultdict(int, dict.fromkeys(reasons, 0))
        tried = 0
        # Trades ruled out by one gain's range without the full check (see
        # gain_windows): only that gain's failure is counted for them
        ruled_out = 0
        # Their combinations never made because they're outside a gain range
        # (see in_range_combinations)
        not_made = 0
        # Why no trade was tried, when none was: the gain whose range left
        # their side empty
        empty_ranges = collections.Counter()
        checks = self.gain_checks()

        def stats():
            self.last_failed.update(
                tried=tried,
                passed=picker.passed,
                failed=invalid_reasons,
                only=only_reasons,
                ruled_out=ruled_out,
                not_made=not_made,
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
            self_mask = side_mask(self_side, self_inventory)
            (
                self_value,
                self_rap,
                self_rap_algo,
                self_demand,
                self_overall_value,
                self_volume,
            ) = get_total_values(self_side, self_item_totals)

            self_count = len(self_side)
            windows = self.gain_windows(
                checks, self_value, self_rap, self_rap_algo, self_overall_value
            )
            counted = [0]
            combinations, range_gain = combinations_for(windows, counted)
            in_range_only = range_gain is not None
            for their_side, their_mask, their_totals, their_count in combinations:
                if self_count == 1 and their_count == 1:
                    continue
                # Checking the clock every pair is slow; every 1024 is enough
                if (
                    self.trade_timeout
                    and not tried & 1023
                    and time.perf_counter() - start_time > self.trade_timeout
                ):
                    break

                # Ensure no overlapping item IDs
                if not self_mask & their_mask:
                    # Fails a gain whatever Robux is added: it can't pass, so
                    # the full check is skipped
                    out = None
                    for index, lowest, highest, reason in windows:
                        amount = their_totals[index]
                        if amount < lowest:
                            out = reason
                            break
                        if amount > highest:
                            out = reason + "_max"
                            break
                    if out:
                        tried += 1
                        ruled_out += 1
                        invalid_reasons[out] += 1
                        continue
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
                        checks=checks,
                    )
                    tried += 1
                    if not reason:
                        if self.debug_print:
                            log(
                                f"[DEBUG] Trade algorithm: validated trade {picker.passed + 1}",
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

                        # Upgrade: you give more items than you get
                        upgrade = num_items_self > num_items_their

                        # Downgrade: you get more items than you give
                        downgrade = num_items_their > num_items_self

                        picker.add(
                            {
                                # NOTE: total = Sum of trade
                                "self_side": self_side,
                                "self_side_item_ids": self_side_item_ids,
                                "self_robux": send_robux,
                                "their_side": their_side,
                                "their_side_item_ids": {
                                    their_inventory[key]["item_id"] for key in their_side
                                },
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
                                "projected_given": (
                                    len(self_projected.intersection(self_side))
                                    if self_projected
                                    else 0
                                ),
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
                            and picker.passed > self.max_valid_trades
                        ):
                            log("[TRADING] Hit Stop After Passing Trades, picking from those", dontPrint=True)
                            stats()
                            return pick_trade()

                    else:
                        for failure in reason:
                            invalid_reasons[failure] += 1
                        if len(reason) == 1:
                            only_reasons[reason[0]] += 1
            else:
                # Combinations outside the gain range were never made
                if in_range_only:
                    not_made += all_their_count - counted[0]
                if in_range_only and not counted[0]:
                    empty_ranges[range_gain] += 1

        stats()
        if picker.passed:
            return pick_trade()
        if not tried:
            self.last_failed["why_none"] = self.why_no_trades(
                self_keys, their_keys, self_inventory, their_inventory, empty_ranges,
            )

        log(
            f"[TRADING] {about}no trade passed your config.\n"
            + failed_text(self.last_failed),
            dontPrint=counter_trade,
        )
        return None

    def why_no_trades(
        self, self_keys, their_keys, self_inventory, their_inventory, empty_ranges=None,
    ):
        """Why there were no trades to try at all, in words."""
        def items(n):
            return f"{n} usable item{'' if n == 1 else 's'}"

        if len(their_keys) < max(1, self.min_items_their):
            return (
                f"They have {items(len(their_keys))} (after your item filters), "
                f"but Min Items Theirs is {self.min_items_their}."
            )
        if len(self_keys) < max(1, self.min_items_self):
            return (
                f"You have {items(len(self_keys))}, but Min Items Yours is "
                f"{self.min_items_self}."
            )
        if len(self_keys) == 1 and len(their_keys) == 1:
            return "Both sides have 1 usable item, and 1-for-1 trades aren't made."
        mine = {self_inventory[k]["item_id"] for k in self_keys}
        if mine.issuperset(their_inventory[k]["item_id"] for k in their_keys):
            return "They only have items you already own."
        if empty_ranges:
            gain = empty_ranges.most_common(1)[0][0]
            low, high = {
                "overall_gain": (self.min_overall_gain, self.max_overall_gain),
                "rap_gain": (self.min_rap_gain, self.max_rap_gain),
                "algo_gain": (self.min_algo_gain, self.max_algo_gain),
                "value_gain": (self.min_value_gain, self.max_value_gain),
            }.get(gain, (None, None))
            name = reason_text(gain).replace(" (below min)", "")
            text = (
                f"None of their item combinations fit your {name} range "
                f"(min {gain_text(low)}, max {gain_text(high)}) for any of your sides."
            )
            return text
        return "Every combination was 1-for-1 or had the same item on both sides."

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
        checks=None,
    ) -> list:
        """
        Every setting the trade fails, in the order they're checked (Robux
        already added). first_only: stop at the first one. checks: from
        gain_checks, worked out once per search. Runs for every combination,
        so it's written for speed.
        """
        overall_b, rap_b, algo_b, value_b = checks or self.gain_checks()
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

        if overall_b:
            miss = gain_miss(
                their_overall_value - self_overall_value, self_overall_value, overall_b
            )
            if miss:
                failures.append("overall_gain" if miss == BELOW_MIN else "overall_gain_max")
                if first_only:
                    return failures
        if rap_b:
            miss = gain_miss(their_rap - self_rap, self_rap, rap_b)
            if miss:
                failures.append("rap_gain" if miss == BELOW_MIN else "rap_gain_max")
                if first_only:
                    return failures
        if algo_b:
            miss = gain_miss(their_rap_algo - self_rap_algo, self_rap_algo, algo_b)
            if miss:
                failures.append("algo_gain" if miss == BELOW_MIN else "algo_gain_max")
                if first_only:
                    return failures
        if value_b and not (
            # No valued items in the trade: nothing for Value Gain to measure
            not self_value and not their_value and self.skip_value_without_valued
        ):
            miss = gain_miss(their_value - self_value, self_value, value_b)
            if miss:
                failures.append("value_gain" if miss == BELOW_MIN else "value_gain_max")
                if first_only:
                    return failures

        return failures

    def gain_windows(
        self, checks, self_value, self_rap, self_algo, self_overall
    ) -> list:
        """
        For each gain that's set: the lowest and highest their side can have
        and still pass it, whatever Robux generate_trade adds (0 up to half
        your RAP, at most Max Robux). A trade outside one fails that gain for
        sure, so the rest of it doesn't need checking. Widened by 1 so
        rounding can't rule out a trade that passes.
        Returns [(index in their totals, lowest, highest, reason)].
        """
        overall_b, rap_b, algo_b, value_b = checks
        robux = 0
        if self.trade_robux and self.max_robux:
            robux = max(0, min(self_rap * 0.5, self.max_robux))
        gains = [
            # (bounds, their totals index, your side, base for %, Robux counts)
            (overall_b, 4, self_overall, self_overall, True, "overall_gain"),
            (rap_b, 1, self_rap, self_rap, True, "rap_gain"),
            (algo_b, 2, self_algo, self_algo, True, "algo_gain"),
        ]
        if not self.skip_value_without_valued:
            gains.append((value_b, 0, self_value, self_value, False, "value_gain"))

        windows = []
        for bounds, index, yours, base, with_robux, reason in gains:
            if not bounds:
                continue
            low, low_percentage, high, high_percentage = bounds
            # A % of a side worth 0 counts as 0 profit: don't guess there
            if (low_percentage or high_percentage) and base <= 0:
                continue
            added = (0, robux) if with_robux else (0,)

            def needed(limit, percentage, r):
                return yours + r + (limit / 100 * (base + r) if percentage else limit)

            lowest = (
                min(needed(low, low_percentage, r) for r in added) - 1
                if low is not None
                else -math.inf
            )
            highest = (
                max(needed(high, high_percentage, r) for r in added) + 1
                if high is not None
                else math.inf
            )
            windows.append((index, lowest, highest, reason))
        return windows

    def gain_checks(self) -> tuple:
        """
        Bounds of every gain setting (None = not set), for trade_failures.
        Worked out from the current settings.
        """
        def bounds(low, high):
            return None if low is None and high is None else gain_bounds(low, high)

        return (
            bounds(self.min_overall_gain, self.max_overall_gain),
            bounds(self.min_rap_gain, self.max_rap_gain),
            bounds(self.min_algo_gain, self.max_algo_gain),
            bounds(self.min_value_gain, self.max_value_gain),
        )

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
