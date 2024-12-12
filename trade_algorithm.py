from handler.handle_config import ConfigHandler
from itertools import combinations, product
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import math

import time
class TradeMaker():
    def __init__(self, config=ConfigHandler('config.cfg')):
        self.config = config

        self.min_rap_gain = self.config.trading['Minimum_RAP_Gain']
        self.max_rap_gain = self.config.trading['Maximum_RAP_Gain']
        self.min_algo_gain = self.config.trading['Minimum_Algo_Gain']
        self.max_algo_gain = self.config.trading['Maximum_Algo_Gain']

        #print(self.min_rap_gain, self.max_rap_gain, "hay")
        self.min_value_gain = self.config.trading['Minimum_Value_Gain']
        self.max_value_gain = self.config.trading['Maximum_Value_Gain']
        self.min_score_percentage = self.config.trading['MinScorePercentage']
        self.max_score_percentage = self.config.trading['MaxScorePercentage']

        self.min_items_self = self.config.trading['MinimumItemsYourSide']
        self.max_items_self = self.config.trading['MaximumItemsYourSide']

        self.min_items_their = self.config.trading['MinimumItemsTheirSide']
        self.max_items_their = self.config.trading['MaximumItemsTheirSide']
        self.select_by = self.config.trading['Select_Trade_Using']

        self.max_robux = self.config.trading['MaxRobux']
        self.robux_divide = self.config.trading['RobuxDividePercentage']
        self.trade_robux = self.config.trading['TradeRobux']

        self.min_sum_of_trade = self.config.trading['MinimumSumOfTrade']

    def select_trade(self, valid_trades, select_by='lowest_rap_gain'):
        """
            Returns the trade that matches the sort arg
        """
        if select_by == 'lowest_demand':
            return min(valid_trades, key=lambda trade: trade['demand'])

        elif select_by  == 'random':
            return random.choice(valid_trades)

        elif select_by == 'highest_demand':
            return max(valid_trades, key=lambda trade: trade['demand'])
            
        elif select_by == 'highest_sum_of_trade':
            return max(valid_trades, key=lambda trade: trade['total_value'] + trade['total_rap'])

        elif select_by == 'lowest_sum_of_trade':
            return min(valid_trades, key=lambda trade: trade['total_value'] + trade['total_rap'])

        elif select_by == 'closest_score':
            return min(valid_trades, key=lambda trade: abs(trade['score']))

        elif select_by == 'highest_rap_gain':
            return max(valid_trades, key=lambda trade: trade['their_rap'] - trade['self_rap'])

        elif select_by == 'lowest_rap_gain':
            return min(valid_trades, key=lambda trade: trade['their_rap'] - trade['self_rap'])

        
        elif select_by == 'highest_algo_gain':
            return max(valid_trades, key=lambda trade: trade['their_rap_algo'] - trade['self_rap_algo'])

        elif select_by == 'lowest_algo_gain':
            return min(valid_trades, key=lambda trade: trade['their_rap_algo'] - trade['self_rap_algo'])

        elif select_by == 'highest_value_gain':
            return max(valid_trades, key=lambda trade: trade['their_value'] - trade['self_value'])

        elif select_by == 'lowest_value_gain':
            # Filter trades where the gain is not zero
            non_zero_trades = [trade for trade in valid_trades if trade['self_value'] != 0 or trade['their_value'] != 0]

            for trade in valid_trades:
                gain = trade['their_value'] - trade['self_value']
                print(f"Trade: Gain: {gain}")
            if non_zero_trades:
                print(min(non_zero_trades, key=lambda trade: trade['their_value'] - trade['self_value']), "HEYO"*30)
                return min(non_zero_trades, key=lambda trade: trade['their_value'] - trade['self_value'])
            else:
                print(min(valid_trades, key=lambda trade: trade['their_value'] - trade['self_value']), "22"*30)
                return min(valid_trades, key=lambda trade: trade['their_value'] - trade['self_value'])
        elif select_by == 'upgrade':
            # Select the trade with the most "upgrade" (i.e., their side has more items than self side)
            return max(valid_trades, key=lambda trade: (trade['num_items_their'] - trade['num_items_self']))

        elif select_by == 'downgrade':
            # Select the trade with the most "downgrade" (i.e., self side has more items than their side)
            return max(valid_trades, key=lambda trade: (trade['num_items_self'] - trade['num_items_their']))
        else:
            raise ValueError(f"Unknown selection type: {select_by}")

    def generate_trade(self, self_inventory, their_inventory, counter_trade=False, timeout=120):
        """
            Algorithm responsible for generating combinations and validating them..
        """
        start_time = time.time()  # Record the start time


        # TODO: add roblox in the combinations so we open up more trades
        self_keys = list(self_inventory.keys())
        their_keys = list(their_inventory.keys())

        # Generate combinations for both inventories
        self_combinations = self.generate_combinations(self_keys, self.min_items_self, self.max_items_self)
        their_combinations = self.generate_combinations(their_keys, self.min_items_their, self.max_items_their)

        valid_trades = []

        def get_total_values(items, inventory):
            """
            Gets the total value, rap, and demand of a list of items.
            """
            value = 0
            rap = 0
            demand = 0
            rap_algorithm = 0
            total_value = 0
            for key in items:
                item = inventory[key]
            
                value += item['value']
                rap += item['rap']
                rap_algorithm += item['rap_algorithm']
                total_value += item['total_value']

                current_demand = item['demand']
                if current_demand:
                    demand += current_demand

            #print("returning", value, rap, rap_algorithm, demand)
            return value, rap, rap_algorithm, demand, total_value



        for self_side in self_combinations:
            if time.time() - start_time > timeout:
                print("Timeout reached while generating trades.")
                return valid_trades[0] if valid_trades else None
            # Create a set for the current self_side to check against
            self_side_item_ids = {self_inventory[key]['item_id'] for key in self_side}

            for their_side in their_combinations:
                if len(self_side) == 1 and len(their_side) == 1:
                    continue
                their_side_item_ids = {their_inventory[key]['item_id'] for key in their_side}

                # Ensure no overlapping item IDs
                if self_side_item_ids.isdisjoint(their_side_item_ids):

                    self_value, self_rap, self_rap_algo, self_demand, self_total_value = get_total_values(self_side,self_inventory)

                    their_value, their_rap, their_rap_algo, their_demand, their_total_value = get_total_values(their_side, their_inventory)
                    
                    #print(self_rap_algo, their_rap_algo, "gr")
                    send_robux = 0
                    #TODO: check if roblox acc has enough roblox and it it doenst send self.max_robux to remaning robux

                    #calc_robux = round((their_rap - self_rap) // float(2))
                    # round down
                    # NOTE: i tried to calcuate with algo but it didnt go too well
                    # Cap the result at self_rap * 0.5 (Roblox limit)
                    robux_limit = self_rap * 0.5

                    # Calculate the robux
                    calc_robux = math.floor(min((their_rap - self_rap) / 4, robux_limit))

                    if calc_robux > 0 and self.trade_robux:
                        # If calculated robux if more than max robux just use max robux?
                        if calc_robux > self.max_robux:
                            calc_robux = self.max_robux

                        send_robux = calc_robux

                    if self.validate_trade(self_rap, self_rap_algo, self_value, their_rap, their_rap_algo, their_value, robux=send_robux):
                        # Calculate the trade sum (RAP and value)
                        total_value = self_value + their_value
                        total_rap = self_rap + their_rap

                        # Calculate close score (percentage)
                        score = ((their_rap - self_rap) / (their_rap + self_rap)) * 100 if (self_rap + their_rap) != 0 else 0

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
                            'total_value': total_value,
                            'total_rap': total_rap,
                            'score': score,
                            'demand': demand,
                            'upgrade': upgrade,
                            'downgrade': downgrade,
                            'num_items_self': num_items_self,
                            'num_items_their': num_items_their,
                            'self_total': self_total_value,
                            'their_total': their_total_value
                        })

                        # idk the number lol
                        if len(valid_trades) > 1500:
                            break

            if valid_trades:
                # pick random trade to avoid sending the same counter trade
                if counter_trade == True:
                    trade = self.select_trade(valid_trades, select_by="random")
                    return trade

                trade = self.select_trade(valid_trades, select_by=self.select_by.lower())


                # TODO: make it queue multiple trades and then pick the best one based on config
                return trade

        return valid_trades[0] if valid_trades else None

    def check_rap_gain(self, their_rap, self_rap, max_offset=0):
        return self.config.check_gain(their_rap, self_rap, self.min_rap_gain, self.max_rap_gain+max_offset)

    def check_value_gain(self, their_value, self_value, max_offset=0):
        return self.config.check_gain(their_value, self_value, self.min_value_gain, self.max_value_gain+max_offset)

    def check_algo_gain(self, their_algo, self_algo, max_offset=0):
        return self.config.check_gain(their_algo, self_algo, self.min_algo_gain, self.max_algo_gain+max_offset)

    def validate_trade(self, self_rap, self_rap_algo, self_value, their_rap, their_rap_algo, their_value, robux=None, max_offset=0):

        # Max offset is for outbounds
        value_gain = their_value - self_value
        if robux != None and robux != 0:
            # see if value is losing because of robux
            # TODO: test to make sure this is a valid method of doing this
            if (value_gain + robux) < self.min_value_gain:
                # print("robux false")
                return False

            #if robux > calc_robux:
            #    return False

        if self.min_sum_of_trade > self_value + their_value:
            # print("sum of trade", self_value, their_value)
            return False

        # Precompute the total value and RAP for both sides in a single loop
        # Calculate value gain and close percentage
        if self_rap + their_rap == 0:
            close_percentage = 0  # Prevent division by zero
        else:
            close_percentage = ((their_rap - self_rap) / (their_rap + self_rap)) * 100

        # Check if close percentage is within the acceptable range
        if close_percentage < self.min_score_percentage or close_percentage > self.max_score_percentage+max_offset:
            return False

        # Check if RAP gain passes the criteria
        if not self.check_rap_gain(their_rap, self_rap, max_offset):
            # print("rap gain false their, self", their_rap, self_rap)
            return False

        if not self.check_algo_gain(their_rap_algo, self_rap_algo, max_offset):
            # print("algo gain false their, self", their_rap_algo, self_rap_algo)
            return False

        # Check if value gain passes the criteria
        if not self.check_value_gain(their_value, self_value, max_offset):
            # print("valu gain false their, self", their_value, self_value)
            return False

        # print("trade valid")
        return True

    def generate_combinations(self, keys, min_items=1, max_items=4):
        # Ensure valid bounds for min_items and max_items
        if not keys:
            print("Error: Keys list is empty.")
            return []
        
        if len(keys) < min_items:
            print(f"Error: Not enough keys to generate combinations. Keys: {keys}, Min items: {min_items}")
            return []
        
        min_items = max(1, min_items)
        max_items = min(max_items, len(keys))

        # Generate combinations
        all_combinations = []
        for r in range(min_items, max_items + 1):
            all_combinations.extend(combinations(keys, r))
        
        return all_combinations
