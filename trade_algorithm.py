from handler.handle_config import ConfigHandler
from rolimons_api import RolimonAPI
from itertools import combinations, product

import time
class TradeMaker():
    def __init__(self):
        self.config = ConfigHandler('config.cfg')
        self.rolimons = RolimonAPI()

        self.min_rap_gain = self.config.trading['Minimum_RAP_Gain']
        self.max_rap_gain = self.config.trading['Maximum_RAP_Gain']
        self.min_value_gain = self.config.trading['Minimum_Value_Gain']
        self.max_value_gain = self.config.trading['Maximum_Value_Gain']
        self.min_score_percentage = self.config.trading['MinScorePercentage']
        self.max_score_percentage = self.config.trading['MaxScorePercentage']



    def generate_trade(self, self_inventory, their_inventory):
        #print("Got inventories", self_inventory, their_inventory)
        # get all useful rolimon data and apply to inventories

        self_keys = list(self_inventory.keys())
        their_keys = list(their_inventory.keys())

        # all combinations of up to 4 items on each side
        self_combinations = self.generate_combinations(self_keys)
        their_combinations = self.generate_combinations(their_keys)


        # Debug: Print possible trades
        valid_trades = []
        for trade in product(self_combinations, their_combinations):
            self_side, their_side = trade
            if self.validate_trade(self_side, their_side, self_inventory, their_inventory):
                valid_trades.append(trade)
        if len(valid_trades) > 1:
            return valid_trades[0]
        else: 
            return None


        #return possible_trades

    def validate_trade(self,  self_side, their_side, self_inventory, their_inventory):
        self_value = sum(self_inventory[key]['value'] for key in self_side)
        self_rap = sum(self_inventory[key]['rap'] for key in self_side)

        their_value = sum(their_inventory[key]['value'] for key in their_side)
        their_rap = sum(their_inventory[key]['value'] for key in their_side)

        #(Sum_of_Rap(theiritem) - Sum_of_Rap(youritem)) / (Sum_of_Rap(theiritem) + Sum_of_Rap(youritem))

        value_gain = their_value - self_value

        close_percentage = ((their_rap - self_rap) / (their_rap + self_rap))*100


        if close_percentage < self.min_score_percentage or close_percentage > self.max_score_percentage:
            return False

        # Check if RAP gain passes the criteria
        if not self.check_rap_gain(their_rap, self_rap):
            return False

        if not self.check_value_gain(their_value, self_value):
            return False

        #print(self_value, self_rap, "for", their_value, their_rap)#, "value and rap gain:", value_gain, rap_gain, close_percentage*100)#,

        return True

    def check_rap_gain(self, their_rap, self_rap):
        # Calculate the RAP gain
        rap_gain = their_rap - self_rap

        # Check if the minimum RAP gain is a float (i.e., percentage-based)
        if not self.min_rap_gain.is_integer():
            percentage_rap_gain = ((their_rap - self_rap) / their_rap) * 100 if their_rap != 0 else 0
            min_rap_gain = self.min_rap_gain * 100
            max_rap_gain = self.max_rap_gain * 100

            return min_rap_gain <= percentage_rap_gain <= max_rap_gain
        else:
            # If it's not a float, compare the RAP gain as an absolute value
            return rap_gain >= self.min_rap_gain and rap_gain <= self.max_rap_gain

    def check_value_gain(self, their_value, self_value):
        # Calculate the value gain
        value_gain = their_value - self_value

        # Check if the minimum value gain is a float (i.e., percentage-based)
        if not self.min_value_gain.is_integer():
            percentage_value_gain = ((their_value - self_value) / their_value) * 100 if their_value != 0 else 0
            min_value_gain = self.min_value_gain * 100
            max_value_gain = self.max_value_gain * 100

            return min_value_gain <= percentage_value_gain <= max_value_gain
        else:
            # If it's not a float, compare the value gain as an absolute value
            return value_gain >= self.min_value_gain and value_gain <= self.max_value_gain

    def generate_combinations(self, keys):
        # Generate all combinations of up to max_len items
        max_items = 4
        all_combinations = []
        for r in range(1, max_items + 1):
            all_combinations.extend(combinations(keys, r))
        return all_combinations
