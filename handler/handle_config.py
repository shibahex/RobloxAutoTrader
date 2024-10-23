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
            'MinDemand': self.get_int('Trading', 'MinDemand')
        }

    def load_projected_detection(self):
        return {
            'Detect_Rolimons_Projecteds': self.get_boolean('Projected Detection', 'Detect Rolimons Projecteds'),
            'MaxProjectedDifference': self.get_float('Projected Detection', 'MaxProjectedDifference'),
            'MinProjectedDifference': self.get_float('Projected Detection', 'MinProjectedDifference'),
            'MinPriceDifference': self.get_float('Projected Detection', 'MinPriceDifference')
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
                #print(key, value)
                if value is None:
                    raise ValueError(f"Configuration error: '{key}' is missing or invalid.")

