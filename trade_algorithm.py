from handler.handle_config import ConfigHandler
from itertools import combinations, product
from concurrent.futures import ThreadPoolExecutor, TimeoutError


import time
class TradeMaker():
    def __init__(self):
        self.config = ConfigHandler('config.cfg')

        self.min_rap_gain = self.config.trading['Minimum_RAP_Gain']
        self.max_rap_gain = self.config.trading['Maximum_RAP_Gain']
        self.min_value_gain = self.config.trading['Minimum_Value_Gain']
        self.max_value_gain = self.config.trading['Maximum_Value_Gain']
        self.min_score_percentage = self.config.trading['MinScorePercentage']
        self.max_score_percentage = self.config.trading['MaxScorePercentage']

        self.min_items_self = self.config.trading['MinimumItemsYourSide']
        self.max_items_self = self.config.trading['MaximumItemsTheirSide']

        self.min_items_their = self.config.trading['MinimumItemsTheirSide']
        self.max_items_their = self.config.trading['MaximumItemsTheirSide']

    def generate_trade(self, self_inventory, their_inventory):
        self_keys = list(self_inventory.keys())
        their_keys = list(their_inventory.keys())

        # Generate combinations for both inventories
        self_combinations = self.generate_combinations(self_keys, self.min_items_self, self.max_items_self)
        their_combinations = self.generate_combinations(their_keys, self.min_items_their, self.max_items_their)

        # Create sets of item IDs for quick lookup
        print(self_inventory, self_keys)
        self_item_ids = {self_inventory[key]['item_id'] for key in self_keys}
        valid_trades = []

        for self_side in self_combinations:
            # Create a set for the current self_side to check against
            self_side_item_ids = {self_inventory[key]['item_id'] for key in self_side}

            for their_side in their_combinations:
                their_side_item_ids = {their_inventory[key]['item_id'] for key in their_side}

                # Ensure no overlapping item IDs
                if self_side_item_ids.isdisjoint(their_side_item_ids):
                    self_value = 0
                    self_rap = 0
                    for key in self_side:
                        item = self_inventory[key]
                        self_value += item['value']
                        self_rap += item['rap']

                    their_value = 0
                    their_rap = 0
                    for key in their_side:
                        item = their_inventory[key]
                        their_value += item['value']
                        their_rap += item['rap']

                    if self.validate_trade(self_rap, self_value, their_rap, their_value):
                        valid_trades.append((self_side, their_side))
                        if len(valid_trades) > 1:
                            # TODO: make it queue multiple trades and then pick the best one based on config
                            return valid_trades[0]

        return valid_trades[0] if valid_trades else None

    def generate_trade_with_timeout(self, self_inventory, their_inventory, timeout=120):
        # Run generate_trade in a separate thread with a timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.generate_trade, self_inventory, their_inventory)
            try:
                # Wait for the result with the specified timeout
                return future.result(timeout=timeout)
            except TimeoutError:
                print("generate_trade timed out")
                return None  # Return None if the function times out


    def check_rap_gain(self, their_rap, self_rap):
        return self.config.check_gain(their_rap, self_rap, self.min_rap_gain, self.max_rap_gain)

    def check_value_gain(self, their_value, self_value):
        return self.config.check_gain(their_value, self_value, self.min_value_gain, self.max_value_gain)

    def validate_trade(self, self_rap, self_value, their_rap, their_value):
        # Precompute the total value and RAP for both sides in a single loop
        # Calculate value gain and close percentage
        value_gain = their_value - self_value
        if self_rap + their_rap == 0:
            close_percentage = 0  # Prevent division by zero
        else:
            close_percentage = ((their_rap - self_rap) / (their_rap + self_rap)) * 100

        # Check if close percentage is within the acceptable range
        if close_percentage < self.min_score_percentage or close_percentage > self.max_score_percentage:
            return False

        # Check if RAP gain passes the criteria
        if not self.check_rap_gain(their_rap, self_rap):
            return False

        # Check if value gain passes the criteria
        if not self.check_value_gain(their_value, self_value):
            return False

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


    def generate_combinations(self, keys, min_items=1, max_items=4):
        all_combinations = []
        for r in range(min_items, max_items + 1):
            all_combinations.extend(combinations(keys, r))
        return all_combinations
