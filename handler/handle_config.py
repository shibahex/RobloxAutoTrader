import configparser

class ConfigHandler:
    def __init__(self, filename="config.cfg"):
        self.config = configparser.ConfigParser()
        self.config.read(filename)
        
        # Load configuration values into attributes
        self.scan_items = self.load_scan_items()
        self.filter_users = self.load_filter_users()
        self.prediction_algorithm = self.load_prediction_algorithm()
        self.trading = self.load_trading()
        self.projected_detection = self.load_projected_detection()
        self.mass_sender = self.load_mass_sender()
        # Check if config is filled out 
        self.validate_config()
    def convert_gain(self, gain):
        """
        Convert gain to a float or int.
        Treat gains < 1 and > -1 as percentages.
        """
        try:
            gain = float(gain) if '.' in str(gain) else int(gain)
            return gain, abs(gain) < 1  # True if between -1 and 1 (percentage)
        except ValueError:
            raise ValueError(f"Invalid gain value: {gain}")

    def calculate_gain(self, gain, base_value, is_percentage):
        """
        Calculate the gain.
        Convert to percentage if required.
        """
        return (gain / base_value) * 100 if is_percentage else gain

    def check_gain(self, their_value, self_value, min_gain=None, max_gain=None):
        """
        Check if gain is within the specified range.
        """
        gain = their_value - self_value
        min_gain, is_min_percentage = self.convert_gain(min_gain) if min_gain is not None else (None, False)
        max_gain, is_max_percentage = self.convert_gain(max_gain) if max_gain is not None else (None, False)

        # Only calculate gain as a percentage if min or max is marked as percentage
        gain = self.calculate_gain(gain, their_value, is_min_percentage or is_max_percentage)

        if min_gain is not None:
            min_gain = min_gain * 100 if is_min_percentage else min_gain
        if max_gain is not None:
            max_gain = max_gain * 100 if is_max_percentage else max_gain

        # Debug output after calculations
 #       print(f"Calculated Gain: {gain}, Min Gain: {min_gain}, Max Gain: {max_gain}")

        if min_gain is not None and max_gain is not None:
            return min_gain <= gain <= max_gain
        elif min_gain is not None:
            return gain >= min_gain
        elif max_gain is not None:
            return gain <= max_gain
        return True

    def check_rap_gain(self, their_rap, self_rap):
        """
        Check if the RAP gain meets the criteria.
        """
        return self.check_gain(their_rap, self_rap, self.min_rap_gain, self.max_rap_gain)

    def check_value_gain(self, their_value, self_value):
        """
        Check if the value gain meets the criteria.
        """
        return self.check_gain(their_value, self_value, self.min_value_gain, self.max_value_gain)

    def check_rap_gain(self, their_rap, self_rap):
        """
        Check if the RAP gain meets the criteria.
        """
        return self.check_gain(their_rap, self_rap, self.min_rap_gain, self.max_rap_gain)

    def check_value_gain(self, their_value, self_value):
        """
        Check if the value gain meets the criteria.
        """
        return self.check_gain(their_value, self_value, self.min_value_gain, self.max_value_gain)



    def check_rap_gain(self, their_rap, self_rap):
        """
        Check if the RAP gain meets the criteria.
        """
        return self.check_gain(their_rap, self_rap, self.min_rap_gain, self.max_rap_gain)

    def check_value_gain(self, their_value, self_value):
        """
        Check if the value gain meets the criteria.
        """
        return self.check_gain(their_value, self_value, self.min_value_gain, self.max_value_gain)

    def process_trade(self, close_percentage, their_rap, self_rap, their_value, self_value):
        """
        Process the trade based on specified criteria.
        """
        if close_percentage < self.min_score_percentage or close_percentage > self.max_score_percentage:
            return False
        if not self.check_rap_gain(their_rap, self_rap):
            return False
        if not self.check_value_gain(their_value, self_value):
            return False
        return True

    def load_scan_items(self):
        return {
            'Minimum_Value_of_Item': self.get_int('Scan Items', 'Minimum Value of Item'),
            'Minimum_Rap_of_Item': self.get_int('Scan Items', 'Minimum Rap of Item'),
            'Minimum_Owners_of_Item': self.get_int('Scan Items', 'Minimum Owners of Item'),
            'Minimum_Demand_of_Item': self.get_int('Scan Items', 'Minimum Demand of Item'),
            'Minimum_Trend_of_Item': self.get_int('Scan Items', 'Minimum Trend of Item'),
            'Scan_Rares': self.get_boolean('Scan Items', 'Scan Rares'),
            'Scan_Type': self.get_string('Scan Items', 'Scan Type'),
            'Scrape_Rolimon_Ads': self.get_boolean('Scan Items', 'Scrape Rolimon Ads')
        }

    def load_filter_users(self):
        return {
            'Last_Online': self.get_int('Filter Users', 'Last Online'),
            'Last_Traded': self.get_int('Filter Users', 'Last Traded'),
            'Minimum_Total_Value': self.get_int('Filter Users', 'Minimum Total Value'),
            'Minimum_Total_Items': self.get_int('Filter Users', 'Minimum Total Items'),
            'Check_Rolimon_Verified': self.get_boolean('Filter Users', 'Has Rolimon Verfified Badge')
        }

    def load_prediction_algorithm(self):
        return {
            'Predict_Values_of_Your_Inventory': self.get_string('Prediction Algorithm', 'Predict Values of your Inventory'),
            'Predict_Values_of_Their_Inventory': self.get_string('Prediction Algorithm', 'Predict Values of their Inventory'),
            'Max_Over_Pay': self.get_float('Prediction Algorithm', 'Max Over Pay'),
            'Max_Loss': self.get_float('Prediction Algorithm', 'Max Loss'),
            'NFT_from_Prediction': self.get_list_of_ints('Prediction Algorithm', 'NFT from Prediction'),
            'Minimum_Value_to_predict': self.get_int('Prediction Algorithm', 'Minimum Value to predict'),
            'Maximum_Value_to_predict': self.get_int('Prediction Algorithm', 'Maximum Value to predict')
        }

    def load_trading(self):
        return {
            'Minimum_RAP_Gain': self.get_float('Trading', 'Minimum RAP Gain'),
            'Maximum_RAP_Gain': self.get_float('Trading', 'Maximum RAP Gain'),
            'Minimum_Value_Gain': self.get_float('Trading', 'Minimum Value Gain'),
            'Maximum_Value_Gain': self.get_float('Trading', 'Maximum Value Gain'),
            'NFT': self.get_string('Trading', 'NFT'),
            'NFR': self.get_string('Trading', 'NFR'),
            'MinAlgorithmGain': self.get_int('Trading', 'MinAlgorithmGain'),
            'MaxAlgorithmGain': self.get_int('Trading', 'MaxAlgorithmGain'),
            'TradeRobux': self.get_boolean('Trading', 'TradeRobux'),
            'RobuxDividePercentage': self.get_float('Trading', 'RobuxDividePercentage'),
            'MaxRobux': self.get_float('Trading', 'MaxRobux'),
            'MaxScorePercentage': self.get_float('Trading', 'MaxScorePercentage'),
            'MinScorePercentage': self.get_float('Trading', 'MinScorePercentage'),
            'MinimumItemsYourSide': self.get_int('Trading', 'MinimumItemsYourSide'),
            'MaximumItemsYourSide': self.get_int('Trading', 'MaximumItemsYourSide'),
            'MinimumItemsTheirSide': self.get_int('Trading', 'MinimumItemsTheirSide'),
            'MaximumItemsTheirSide': self.get_int('Trading', 'MaximumItemsTheirSide'),
            'MinimumSumOfTrade': self.get_float('Trading', 'MinimumSumOfTrade'),
            'MinDemand': self.get_int('Trading', 'MinDemand'),
            'Select_Trade_Using': self.get_string('Trading', 'Select Trade Using')
        }

    def load_projected_detection(self):
        return {
            'Detect_Rolimons_Projecteds': self.get_boolean('Projected Detection', 'Detect Rolimons Projecteds'),
            'MaximumGraphDifference': self.get_float('Projected Detection', 'Maximum Graph Difference'),
            'MinimumGraphDifference': self.get_float('Projected Detection', 'Minimum Graph Difference'),
            'MinPriceDifference': self.get_float('Projected Detection', 'MinPriceDifference'),
            'AmountofSalestoScan': self.get_int('Projected Detection', 'Amount of sales to scan')
        }

    def load_mass_sender(self):
        return {
            'Enable_Mass_Sending': self.get_boolean('Mass Sender', 'Enable Mass Sending'),
            'Always_send': self.get_list_of_ints('Mass Sender', 'Always send'),
            'Always_Receive': self.get_list_of_ints('Mass Sender', 'Always Receive')
        }

    def get_int(self, section, option):
        try:
            return self.config.getint(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            print(f"Error retrieving integer for [{section}] {option}: {e}")
            return None

    def get_float(self, section, option):
        try:
            return self.config.getfloat(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            print(f"Error retrieving float for [{section}] {option}: {e}")
            return None

    def get_string(self, section, option):
        try:
            return self.config.get(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            print(f"Error retrieving string for [{section}] {option}: {e}")
            return None

    def get_boolean(self, section, option):
        try:
            return self.config.getboolean(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            print(f"Error retrieving boolean for [{section}] {option}: {e}")
            return None

    def get_list_of_ints(self, section, option):
        try:
            if self.config.has_option(section, option):
                return list(map(int, self.config.get(section, option).split(',')))
            return []
        except (ValueError, TypeError) as e:
            print(f"Error retrieving list of integers for [{section}] {option}: {e}")
            return []


    def validate_config(self):
        # Check if any required values are None and raise an error
        for section in [self.scan_items, self.filter_users, self.prediction_algorithm, self.trading, self.projected_detection]:
            for key, value in section.items():
                if value is None:
                    raise ValueError(f"Configuration error: '{key}' is missing or invalid.")

