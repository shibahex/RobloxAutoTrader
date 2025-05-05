from handler.handle_logs import log

import configparser


class ConfigHandler:
    def __init__(self, filename="config.cfg"):
        self.config = configparser.ConfigParser()
        self.config.read(filename)

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
        # self.mass_sender = self.load_mass_sender()
        # Check if config is filled out
        self.validate_config()

    def convert_gain(self, gain):
        """
        Convert gain to a float or int
        Treat gains < 1 and > -1 as percentages.
        """
        try:
            gain = float(gain) if '.' in str(gain) else int(gain)

            if gain == 0.0:
                return gain, False

            return gain, abs(gain) < 1  # True if between -1 and 1 (percentage)
        except ValueError:
            raise ValueError(f"Invalid gain value: {gain}")

    def calculate_gain(self, gain, base_value, is_percentage):
        """
        Calculate the gain.
        Convert to percentage if required.
        """

        if base_value == 0:
            # Adjust fallback behavior as needed.
            return 0 if is_percentage else gain

        return (gain / base_value) * 100 if is_percentage else gain

    def check_gain(self, their_value, self_value, min_gain=False, max_gain=False, max_offset=0):
        """
        Check if gain is within the specified range.
        """
        gain = their_value - self_value

        min_gain, is_min_percentage = self.convert_gain(
            min_gain) if min_gain != None else (None, False)
        max_gain, is_max_percentage = self.convert_gain(
            max_gain) if max_gain != None else (None, False)

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

    def load_discord(self):
        return {
            "Send_Webhook": self.get_string("Discord", "Send Webhook"),
            "Completed_Webhook": self.get_string("Discord", "Completed Webhook"),
        }

    def load_scan_items(self):
        return {
            'Minimum_Value_of_Item': self.get_int('Getting Owners of Items', 'Minimum Value of Item'),
            'Minimum_Rap_of_Item': self.get_int('Getting Owners of Items', 'Minimum Rap of Item'),
            'Minimum_Owners_of_Item': self.get_int('Getting Owners of Items', 'Minimum Owners of Item'),
            'Minimum_Demand_of_Item': self.get_int('Getting Owners of Items', 'Minimum Demand of Item'),
            'Minimum_Trend_of_Item': self.get_int('Getting Owners of Items', 'Minimum Trend of Item'),
            'Scan_Rares': self.get_boolean('Getting Owners of Items', 'Scan Rares'),
            'Scan_Type': self.get_string('Getting Owners of Items', 'Scan Type'),
            'Scrape_Rolimon_Ads': self.get_boolean('Getting Owners of Items', 'Scrape Rolimon Ads')
        }

    def load_filter_users(self):
        return {
            'Minimum_Total_Items': self.get_int('Filtering Users', 'Minimum Total Items'),
        }

    def load_debug(self):
        return {
            'trading_debug': self.get_boolean('debug', 'Show Trade Debug'),
            'ignore_limit': self.get_boolean('debug', 'Ignore trade limit'),
            'dont_send_trade': self.get_boolean('debug', 'Dont Send Trades'),
            'dont_check_outbounds': self.get_boolean('debug', 'Dont Check Outbounds'),
            'show_scanning_users': self.get_boolean('debug', 'Show Scanning Users'),
            'show_scanning_inventory': self.get_boolean('debug', 'Show Scanning Inventory')
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
            'NFT': self.get_list('Filtering Items', 'NFT'),
            'NFR': self.get_list('Filtering Items', 'NFR'),
            'Maximum_Amount_of_Duplicate_Items': self.get_int('Filtering Items', 'Maximum Amount of Duplicate Items'),
            'Maximum_Amount_of_Trader_Duplicate_Items': self.get_int('Filtering Items', 'Maximum Amount of Trader Duplicate Items'),
            'MinDemand': self.get_int('Filtering Items', 'Minimum Valued Item Demand'),
            'MinDailySales': self.get_float('Filtering Items', 'Minimum Daily Sales of Item'),
            'MaxSalesGap': self.get_float('Filtering Items', 'Maximum Average Gaps in Sales'),
        }

    def load_filter_generated(self):
        return {
            'Max_Seconds_Spent_on_One_User': self.get_float('Filtering Generated Trades', 'Max Seconds Spent on One User'),
            'Max_Seconds_Spent_on_Generating_Trades': self.get_float('Filtering Generated Trades', 'Max Seconds Spent on Generating Trades'),
            'Max_Valid_Trades': self.get_float('Filtering Generated Trades', 'Max Valid Trades'),
            'Select_Trade_Using': self.get_string('Filtering Generated Trades', 'Select Trade Using')
        }

    def load_trading(self):
        return {
            'Outbound_Cancel_Offset': self.get_int('Outbound Settings', 'Outbound Minimum Gain Offset to Cancel'),
            'Algo_Cancel_Offset': self.get_int('Outbound Settings', 'RAP Algorithm Gain Offset to Cancel'),
            'Minimum_RAP_Gain': self.get_float('Trading Settings', 'Minimum RAP Gain'),
            'Maximum_RAP_Gain': self.get_float('Trading Settings', 'Maximum RAP Gain'),
            'Minimum_Value_Gain': self.get_float('Trading Settings', 'Minimum Value Gain'),
            'Maximum_Value_Gain': self.get_float('Trading Settings', 'Maximum Value Gain'),
            'Minimum_Overall_Gain': self.get_float('Trading Settings', 'Minimum Overall Value Gain'),
            'Maximum_Overall_Gain': self.get_float('Trading Settings', 'Maximum Overall Value Gain'),
            'Rap_Algo_For_Valued': self.get_string('Trading Settings', 'RAP Algorithm for Valued Items'),
            'Minimum_Algo_Gain': self.get_float('Trading Settings', 'Minimum Rap Algorithm Gain'),
            'Maximum_Algo_Gain': self.get_float('Trading Settings', 'Maximum Rap Algorithm Gain'),
            'TradeRobux': self.get_boolean('Trading Settings', 'Trade Robux'),
            'RobuxDividePercentage': self.get_float('Trading Settings', 'Robux Divide Percentage'),
            'MaxRobux': self.get_float('Trading Settings', 'Max Robux'),
            'MinOverallValueScorePercentage': self.get_float('Trading Settings', 'Min Overall Value Score Percentage'),
            'MaxOverallValueScorePercentage': self.get_float('Trading Settings', 'Max Overall Value Score Percentage'),
            'MinRAPScorePercentage': self.get_float('Trading Settings', 'Min RAP Score Percentage'),
            'MaxRAPScorePercentage': self.get_float('Trading Settings', 'Max RAP Score Percentage'),
            'MinimumItemsYourSide': self.get_int('Trading Settings', 'Minimum Items on Your Side'),
            'MaximumItemsYourSide': self.get_int('Trading Settings', 'Maximum Items on Your Side'),
            'MinimumItemsTheirSide': self.get_int('Trading Settings', 'Minimum Items on Their Side'),
            'MaximumItemsTheirSide': self.get_int('Trading Settings', 'Maximum Items on Their Side'),
            'MinimumValueOfTrade': self.get_float('Trading Settings', 'Minimum Value Sum Of Trade'),
            'MinimumRapOfTrade': self.get_float('Trading Settings', 'Minimum Rap Sum Of Trade'),
        }

    def load_inbounds(self):
        return {
            'CounterTrades': self.get_boolean('Inbound Settings', 'Counter Trades'),
            'Dont_Counter_Wins': self.get_boolean('Inbound Settings', 'Dont Counter Wins')

        }

    def load_projected_detection(self):
        return {
            'Detect_Rolimons_Projecteds': self.get_boolean('Projected Detection', 'Detect Rolimons Projecteds'),
            'MaximumGraphDifference': self.get_float('Projected Detection', 'Maximum Graph Difference'),
            'MinimumGraphDifference': self.get_float('Projected Detection', 'Minimum Graph Difference'),
            'MinPriceDifference': self.get_float('Projected Detection', 'MinPriceDifference'),
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
            log(f"Error retrieving integer for [{section}] {option}: {e}")
            return "Not Set"

    def get_float(self, section, option):
        try:
            return self.config.getfloat(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            # log(f"Error retrieving float for [{section}] {option}: {e}")
            try:
                string = self.get_string(section, option)
                if string.lower() == "false" or string.lower() == "none":
                    return None
            except:
                pass
            return "Not Set"

    def get_string(self, section, option):
        try:
            return self.config.get(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            log(f"Error retrieving string for [{section}] {option}: {e}")
            return "Not Set"

    def get_boolean(self, section, option):
        try:
            return self.config.getboolean(section, option) if self.config.has_option(section, option) else None
        except (ValueError, TypeError) as e:
            log(f"Error retrieving boolean for [{section}] {option}: {e}")
            return "Not Set"

    def get_list(self, section, option):
        try:
            if self.config.has_option(section, option):
                values = self.config.get(section, option).split(',')

                # Filter out invalid values (None or empty string)
                valid_values = [v for v in values if v and v != 'None']

                return valid_values
            return []
        except (ValueError, TypeError) as e:
            log(f"Error retrieving list of integers for [{
                section}] {option}: {e}")
            return []

    def validate_config(self):
        # Check if any required values are None and raise an error
        for section in [self.scan_items, self.filter_users, self.trading, self.projected_detection]:
            for key, value in section.items():
                if value == "Not Set":
                    raise ValueError(f"Configuration error: '{
                                     key}' is missing or invalid.")
