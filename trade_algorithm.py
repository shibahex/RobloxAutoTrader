from handler.handle_config import ConfigHandler
from itertools import combinations, product
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import math
import random

import time


class TradeMaker():
    def __init__(self, config=ConfigHandler('config.cfg'), is_outbound_checker=False):
        self.config = config

        self.min_rap_gain = self.config.trading['Minimum_RAP_Gain']
        self.max_rap_gain = self.config.trading['Maximum_RAP_Gain']

        self.min_overall_gain = self.config.trading['Minimum_Overall_Gain']
        self.max_overall_gain = self.config.trading['Maximum_Overall_Gain']

        self.min_algo_gain = self.config.trading['Minimum_Algo_Gain']
        self.max_algo_gain = self.config.trading['Maximum_Algo_Gain']

        # print(self.min_rap_gain, self.max_rap_gain, "hay")
        self.min_value_gain = self.config.trading['Minimum_Value_Gain']
        self.max_value_gain = self.config.trading['Maximum_Value_Gain']

        self.min_rap_score_percentage = self.config.trading['MinRAPScorePercentage']
        self.max_rap_score_percentage = self.config.trading['MaxRAPScorePercentage']

        self.min_overall_score_percentage = self.config.trading['MinOverallValueScorePercentage']
        self.max_overall_score_percentage = self.config.trading['MaxOverallValueScorePercentage']

        self.min_items_self = self.config.trading['MinimumItemsYourSide']
        self.max_items_self = self.config.trading['MaximumItemsYourSide']

        self.min_items_their = self.config.trading['MinimumItemsTheirSide']
        self.max_items_their = self.config.trading['MaximumItemsTheirSide']
        self.select_by = self.config.filter_generated['Select_Trade_Using']

        self.max_robux = self.config.trading['MaxRobux']
        self.robux_divide = self.config.trading['RobuxDividePercentage']
        self.trade_robux = self.config.trading['TradeRobux']

        self.min_value_of_trade = self.config.trading['MinimumValueOfTrade']
        self.min_rap_of_trade = self.config.trading['MinimumRapOfTrade']

        self.max_valid_trades = self.config.filter_generated['Max_Valid_Trades']
        self.trade_timeout = self.config.filter_generated['Max_Seconds_Spent_on_Generating_Trades']

        self.debug_print = self.config.debug['trading_debug']

        self.outbound_cancel_offset = self.config.trading['Outbound_Cancel_Offset']
        self.algo_outbound_offset = self.config.trading['Algo_Cancel_Offset']
        if is_outbound_checker == True:
            if self.min_rap_gain is not None:
                self.min_rap_gain = max(
                    0, self.min_rap_gain - self.outbound_cancel_offset) if self.min_rap_gain >= 0 else self.min_rap_gain - self.outbound_cancel_offset

            if self.min_overall_gain is not None:
                self.min_overall_gain = max(
                    0, self.min_overall_gain - self.outbound_cancel_offset) if self.min_overall_gain >= 0 else self.min_overall_gain - self.outbound_cancel_offset

            if self.min_algo_gain is not None:
                self.min_algo_gain = max(
                    0, self.min_algo_gain - self.algo_outbound_offset) if self.min_algo_gain >= 0 else self.min_algo_gain - self.algo_outbound_offset

            print(f"Cancel trades that go below: [min algo gain: {self.min_algo_gain}, min overall gain: {
                  self.min_overall_gain}, min rap gain: {self.min_rap_gain}]")

            self.max_rap_gain = None
            self.max_algo_gain = None
            self.max_value_gain = None
            self.max_overall_gain = None

            self.min_rap_score_percentage = None
            self.max_rap_score_percentage = None

            self.min_overall_score_percentage = None
            self.max_overall_score_percentage = None

    def select_trade(self, valid_trades, select_by='lowest_rap_gain'):
        """
            Returns the trade that matches the sort arg
        """

        select_by = select_by.lower()
        if select_by == 'lowest_demand':
            return min(valid_trades, key=lambda trade: trade['demand'])

        elif select_by == 'random':
            return random.choice(valid_trades)

        elif select_by == 'highest_volume_gain':
            return max(valid_trades, key=lambda trade: trade['their_volume'] - trade['self_volume'])

        elif select_by == 'lowest_volume_gain':
            return min(valid_trades, key=lambda trade: trade['their_volume'] - trade['self_volume'])

        elif select_by == 'highest_sum_of_volume':
            return max(valid_trades, key=lambda trade: trade['total_volume'])

        elif select_by == 'lowest_sum_of_volume':
            return min(valid_trades, key=lambda trade: trade['total_volume'])

        elif select_by == 'highest_demand':
            return max(valid_trades, key=lambda trade: trade['demand'])

        elif select_by == 'highest_sum_of_trade_value':
            return max(valid_trades, key=lambda trade: trade['total_value'])

        elif select_by == 'lowest_sum_of_trade_value':
            return min(valid_trades, key=lambda trade: trade['total_value'])

        elif select_by == 'highest_sum_of_trade_rap':
            return max(valid_trades, key=lambda trade: trade['total_rap'])

        elif select_by == 'lowest_sum_of_trade_rap':
            return min(valid_trades, key=lambda trade: trade['total_rap'])

        elif select_by == 'highest_sum_of_overall_value':
            return max(valid_trades, key=lambda trade: trade['total_overall_value'])

        elif select_by == 'lowest_sum_of_overall_value':
            return min(valid_trades, key=lambda trade: trade['total_overall_value'])

        elif select_by == 'closest_score_based_on_overall_value':
            return min(valid_trades, key=lambda trade: abs(trade['overall_close_score']))

        elif select_by == 'closest_score_based_on_rap':
            return min(valid_trades, key=lambda trade: abs(trade['rap_close_score']))

        elif select_by == 'highest_rap_gain':
            return max(valid_trades, key=lambda trade: trade['their_rap'] - trade['self_rap'])

        elif select_by == 'lowest_rap_gain':
            return min(valid_trades, key=lambda trade: trade['their_rap'] - trade['self_rap'])

        elif select_by == 'highest_algo_gain':
            return max(valid_trades, key=lambda trade: trade['their_rap_algo'] - trade['self_rap_algo'])

        elif select_by == 'lowest_algo_gain':
            return min(valid_trades, key=lambda trade: trade['their_rap_algo'] - trade['self_rap_algo'])

        elif select_by == 'highest_overall_gain':
            return max(valid_trades, key=lambda trade: trade['their_overall_value'] - trade['self_overall_value'])

        elif select_by == 'lowest_overall_gain':
            return min(valid_trades, key=lambda trade: trade['their_overall_value'] - trade['self_overall_value'])

        elif select_by == 'highest_value_gain':
            return max(valid_trades, key=lambda trade: trade['their_value'] - trade['self_value'])

        elif select_by == 'lowest_value_gain':
            # Filter trades where the gain is not zero
            non_zero_trades = [
                trade for trade in valid_trades if trade['self_value'] != 0 or trade['their_value'] != 0]

            for trade in valid_trades:
                gain = trade['their_value'] - trade['self_value']
            if non_zero_trades:
                return min(non_zero_trades, key=lambda trade: trade['their_value'] - trade['self_value'])
            else:
                return min(valid_trades, key=lambda trade: trade['their_value'] - trade['self_value'])
        elif select_by == 'upgrade':
            # Select the trade with the most "upgrade" (i.e., their side has more items than self side)
            return max(valid_trades, key=lambda trade: (trade['num_items_their'] - trade['num_items_self']))

        elif select_by == 'downgrade':
            # Select the trade with the most "downgrade" (i.e., self side has more items than their side)
            return max(valid_trades, key=lambda trade: (trade['num_items_self'] - trade['num_items_their']))
        else:
            raise ValueError(f"Unknown selection type: {select_by}")

    def generate_trade(self, self_inventory, their_inventory, counter_trade=False):
        """
            Algorithm responsible for generating combinations and validating them..
            if its a counter trade it will select random trade to send back
        """
        valid_trades = []

        def pick_trade():
            # pick random trade to avoid sending the same counter trade
            if counter_trade == True:
                trade = self.select_trade(valid_trades, select_by="random")
                return trade

            trade = self.select_trade(
                valid_trades, select_by=self.select_by.lower())
            return trade
        start_time = time.perf_counter()  # Use perf_counter for better precision

        if self.debug_print == True:
            print("trade algorithm: getting keys")

        if not self_inventory or not their_inventory:
            print('[Debug] in generating trade invalid inventory, returning None')
            return None

        self_keys = list(self_inventory.keys())
        their_keys = list(their_inventory.keys())
        if self.debug_print == True:
            print("Trade algorithm got keys")

        def get_total_values(items, inventory):
            """
            Gets the total value, rap, and demand of a list of items.
            """
            value, rap, rap_algorithm, demand, total_value, volume = 0, 0, 0, 0, 0, 0

            def get_value(item, value):
                if item[value] != None:
                    return item[value]
                else:
                    print(item, "doesnt have", value)
                    return 0

            for key in items:
                item = inventory[key]

                rap += get_value(item, 'rap')
                rap_algorithm += get_value(item, 'rap_algorithm')

                value += get_value(item, 'value')
                total_value += get_value(item, 'total_value')
                volume += get_value(item, 'item_volume')

                current_demand = item['demand']
                if current_demand:
                    demand += current_demand

            return value, rap, rap_algorithm, demand, total_value, volume

        if self.debug_print == True:
            print("Trade algorithm: starting trade generation")
        # NOTE: have like: out of 30000 trades, 4 valid: 400 failed sum of trade blah

        pre_checks = [self.min_rap_gain, self.min_value_gain,
                      self.min_overall_gain, self.min_algo_gain]
        invalid_reasons = {"value_gain": 0, "min_rap_of_trade": 0, "min_value_of_trade": 0, "close_perc": 0,
                           "rap_gain": 0, "algo_gain": 0, "overall_gain": 0, "overall_close_percentage": 0, "rap_close_percentage": 0}
        for self_side in self.generate_combinations(self_keys, self.min_items_self, self.max_items_self):
            # print(time.perf_counter() - start_time, timeout, "first scope")
            if self.trade_timeout and time.perf_counter() - start_time > self.trade_timeout:
                print(
                    "Timeout reached while generating trades. invalid reasons:", invalid_reasons)
                break
            # Create a set for the current self_side to check against
            self_side_item_ids = {
                self_inventory[key]['item_id'] for key in self_side}

            for their_side in self.generate_combinations(their_keys, self.min_items_their, self.max_items_their):
                if len(self_side) == 1 and len(their_side) == 1:
                    continue
                # print(time.perf_counter() - start_time, timeout)
                if self.trade_timeout and time.perf_counter() - start_time > self.trade_timeout:
                    break

                their_side_item_ids = {
                    their_inventory[key]['item_id'] for key in their_side}

                # Ensure no overlapping item IDs
                if self_side_item_ids.isdisjoint(their_side_item_ids):
                    self_value, self_rap, self_rap_algo, self_demand, self_overall_value, self_volume = get_total_values(
                        self_side, self_inventory)
                    their_value, their_rap, their_rap_algo, their_demand, their_overall_value, their_volume = get_total_values(
                        their_side, their_inventory)

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
                        min((their_rap - self_rap) / 4, robux_limit))

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
                            print("[DEBUG] Trade algorithm: validated trade", len(
                                valid_trades))

                        # Calculate the trade sum (RAP and value)
                        total_value = self_value + their_value
                        total_rap = self_rap + their_rap
                        total_overall_value = self_overall_value + their_overall_value
                        total_volume = self_volume + their_volume

                        # Calculate close score (percentage)
                        # TODO: maybe we could optimize this by having ONE function do it then return it.
                        # Because Right now we are doing this while generating the trade and here
                        rap_close_percentage = self.close_percentage(
                            self_value=self_rap, their_value=their_rap)
                        overall_close_percentage = self.close_percentage(
                            self_value=self_overall_value, their_value=their_overall_value)

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
                        valid_trades.append({
                            # NOTE: total = Sum of trade
                            'self_side': self_side,
                            'self_side_item_ids': self_side_item_ids,
                            'self_robux': send_robux,
                            'their_side': their_side,
                            'their_side_item_ids': their_side_item_ids,
                            'self_value': self_value,
                            'their_value': their_value,
                            'self_rap': self_rap,
                            'their_rap': their_rap,
                            'self_rap_algo': self_rap_algo,
                            'their_rap_algo': their_rap_algo,
                            'self_volume': self_volume,
                            'their_volume': their_volume,
                            'total_value': total_value,
                            'total_rap': total_rap,
                            'total_overall_value': total_overall_value,
                            'total_volume': total_volume,
                            'rap_close_score': rap_close_percentage,
                            'overall_close_score': overall_close_percentage,
                            'demand': demand,
                            'upgrade': upgrade,
                            'downgrade': downgrade,
                            'num_items_self': num_items_self,
                            'num_items_their': num_items_their,
                            'self_overall_value': self_overall_value,
                            'their_overall_value': their_overall_value
                        })

                        # idk the number lol
                        # TODO: MAKE THIS IN CONFIG
                        if self.max_valid_trades and len(valid_trades) > self.max_valid_trades:
                            print("Trade algorithm: valid trade limits reached")
                            return pick_trade()

                    else:
                        # print("Not valid", self_side_item_ids, "for", their_side_item_ids)
                        if reason in invalid_reasons:
                            invalid_reasons[reason] += 1

        if valid_trades:
            return pick_trade()

        print("Couldnt find valid_trades heres invalid trades reasons:",
              invalid_reasons)
        return None

    def check_rap_gain(self, their_rap, self_rap):
        return True
        return self.config.check_gain(their_rap, self_rap, self.min_rap_gain, self.max_rap_gain)

    def check_value_gain(self, their_value, self_value):
        return True
        return self.config.check_gain(their_value, self_value, self.min_value_gain, self.max_value_gain)

    def check_algo_gain(self, their_algo, self_algo):
        return True
        return self.config.check_gain(their_algo, self_algo, self.min_algo_gain, self.max_algo_gain)

    def check_overall_gain(self, their_overall, self_overall):
        return self.config.check_gain(their_overall, self_overall, self.min_overall_gain, self.max_overall_gain)

    def close_percentage(self, self_value, their_value):
        # Calculate value gain and close percentage
        if self_value + their_value == 0 or their_value - self_value == 0:
            close_percentage = 0  # Prevent division by zero
        else:
            close_percentage = ((their_value - self_value) /
                                (their_value + self_value)) * 100

        return close_percentage

    def validate_trade(self, self_rap, self_rap_algo, self_value, their_rap, their_rap_algo, their_value, self_overall_value, their_overall_value, robux=None):
        value_gain = their_value - self_value
        if robux != None and robux != 0:
            # see if value is losing because of robux
            # TODO: test to make sure this is a valid method of doing this
            if self.min_value_gain and (value_gain + robux) < self.min_value_gain:
                # print("robux false")
                return False, "value_gain"

            # if robux > calc_robux:
            #    return False

        if self.min_value_of_trade != False and self.min_value_of_trade > self_value + their_value:
            # print("sum of trade", self_value, their_value)
            return False, "min_value_of_trade"

        if self.min_rap_of_trade != False and self.min_rap_of_trade > self_rap + their_rap:
            return False, "min_rap_of_trade"

        # Precompute the total value and RAP for both sides in a single loop
        # Calculate value gain and close percentage
        rap_close_percentage = self.close_percentage(
            self_value=self_rap, their_value=their_rap)
        overall_close_percentage = self.close_percentage(
            self_value=self_overall_value, their_value=their_overall_value)
        # Check if close percentage is within the acceptable range
        if self.min_overall_score_percentage and overall_close_percentage < self.min_overall_score_percentage or self.max_overall_score_percentage and overall_close_percentage > self.max_overall_score_percentage:
            return False, "overall_close_percentage"

        if self.min_rap_score_percentage and rap_close_percentage < self.min_rap_score_percentage or self.min_rap_score_percentage and rap_close_percentage > self.max_rap_score_percentage:
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
            print("Error: Keys list is empty.")
            return
            # Returning an empty generator

        if len(keys) < min_items:
            print(f"Error: Not enough keys to generate combinations. Keys: {
                  keys}, Min items: {min_items}")
            print("Ignoring to send trades")
            # return

        # Adjust bounds for min_items and max_items
        min_items = max(1, min_items)
        max_items = min(max_items, len(keys))

        # Lazily generate combinations for each size
        for r in range(min_items, max_items + 1):
            for combination in combinations(keys, r):
                yield combination  # Yield one combination at a time
