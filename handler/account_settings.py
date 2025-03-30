import json
from handler.handle_json import JsonHandler
from handler.handle_config import ConfigHandler
import configparser
import os
import time
#from handle_confing import ConfigHandler
class HandleConfigs:
    def __init__(self):
        self.acc_configs =  JsonHandler("account_configs.jsonc")
        self.cookies = JsonHandler("cookies.json")
        self.default_config = ConfigHandler().trading

    def get_config(self, user_id):
        """Retrieve the configuration for a specific user ID."""
        data = self.acc_configs.read_data()
        return data.get(user_id, {})

    def check_for_updates(self):
        self.acc_configs.update_missing_config(self.default_config)

    def select_user_id(self):
        """Prompt the user to select a user ID from available keys."""
        # TODO: SHOW USERNAME
        # TODO: add option to reset a config to default
        data = self.acc_configs.read_data()
        user_ids = list(data.keys())
        if not user_ids:
            print("no user configurations found.")
            return False

        print("\nSelect a user ID to configure:")
        for i, user_id in enumerate(user_ids, 1):
            print(f"{i}. {user_id}", self.cookies.return_name_from_id(str(user_id)))

        try:
            choice = int(input("\nEnter the number of the user ID: "))
            if choice < 1 or choice > len(user_ids):
                raise ValueError
            return user_ids[choice - 1]
        except ValueError:
            print("Invalid input. Exiting.")
            return None

    def show_presets(self):
        directory = "./configs"
        file_names = os.listdir(directory)
        for enum, file in enumerate(os.listdir(directory)):
            if file.endswith(".cfg"):
                file_path = os.path.join(directory, file)
                config = configparser.ConfigParser()

                try:
                    config.read(file_path)
                except Exception as e:
                    print("Couldn't read config", e)
                    continue

                if 'Info' in config and 'Description' in config['Info']:
                    print(f"({enum+1})", file, "|", config['Info']['Description'])
                else:
                    print(f"({enum+1})", file, "|", "Config Doesn't have descriptions")

        try:
            chosen = int(input("\nPlease Enter the Number of the Config you want to use > ")) - 1 
            if chosen <= len(file_names):
                chosen_config = file_names[chosen]
                with open(f"{directory}/{chosen_config}", "r") as f:
                    config_contents = f.read()

                with open("./config.cfg", "w") as f:
                    f.write(config_contents)

                print(f"\nReplaced './config.cfg' with the contents of '{file_names[chosen]}'")
                time.sleep(1)
        except Exception as e:
            print("Invalid Choice", e)
            time.sleep(3)
            return


        
        
    def show_config(self, user_id=None):
        """List grouped and single keys in a user's configuration."""
        if user_id is None:
            user_id = self.select_user_id()
        if not user_id:
            return {}, []

        data_config = self.get_config(user_id)
        if not data_config:
            print(f"No configuration found for user ID {user_id}.")
            return {}, []

        grouped_keys = {}
        single_keys = []

        for key in data_config:
            if key.startswith("Minimum_"):
                base_name = key[8:]
                max_key = f"Maximum_{base_name}"
                if max_key in data_config:
                    grouped_keys[base_name] = (key, max_key)
            elif not any(key in group for group in grouped_keys.values()):
                single_keys.append(key)

        print("\nConfigurations:")
        for i, (name, (min_key, max_key)) in enumerate(grouped_keys.items(), 1):
            print(f"{i}. {name}: Min = {data_config[min_key]}, Max = {data_config[max_key]}")
        for j, key in enumerate(single_keys, len(grouped_keys) + 1):
            print(f"{j}. {key}: {data_config[key]}")

        return grouped_keys, single_keys

    def create_config(self):
        json_handler = JsonHandler('cookies.json')

        json_handler.list_cookies(check_config=True)
        index=input("Enter number to create config from (Press enter to quit): ")
        if index == None or index == '':
            return

        
        user_id = json_handler.return_userid_from_index(index, check_config=True)

        if user_id == False:
            print("Couldnt find userid")
            time.sleep(3)
            return

        data = self.acc_configs.read_data()
        data[user_id] = self.default_config
        self.acc_configs.write_data(data)

    def delete_config(self, user_id=None):
        if user_id == None:
            user_id = self.select_user_id()
            if not user_id:
                # Do nothing if they pressed enter
                return
        data = self.acc_configs.read_data()
        try:
            del data[user_id]
        except Exception as e:
            print("Couldnt delete config:", e)
        self.acc_configs.write_data(data)

    def edit_config(self):
        """Edit a user's configuration interactively until they quit."""
        user_id = self.select_user_id()
        if not user_id:
            return
        while True:
            data_config = self.get_config(user_id)
            if not data_config:
                print(f"No configuration found for user ID {user_id}.")
                return

            grouped_keys, single_keys = self.show_config(user_id)

            options = list(grouped_keys.keys()) + single_keys

            try:
                choice_input = input("\nEnter the number of the configuration to edit (or type 'quit' to exit): ")
                if choice_input.strip().lower() == 'quit' or not choice_input.strip():
                    print("Exiting the configuration editor.")
                    break

                choice = int(choice_input)
                if choice < 1 or choice > len(options):
                    raise ValueError
            except ValueError:
                print("Invalid input. Please try again.")
                continue

            selected_option = options[choice - 1]

            if selected_option in grouped_keys:
                min_key, max_key = grouped_keys[selected_option]
                for key in (min_key, max_key):
                    self.prompt_and_update(data_config, key)
            else:
                self.prompt_and_update(data_config, selected_option)

            all_data = self.acc_configs.read_data()
            all_data[user_id] = data_config
            self.acc_configs.write_data(all_data)
            print("Data successfully written to account_configs.jsonc.")
            



    def prompt_and_update(self, data_config, key):
        """Prompt the user to update a configuration value."""
        current_value = data_config[key]

        if key == "Select_Trade_Using":
            options = [
                "highest_demand", "lowest_demand", "highest_sum_of_trade", 
                "lowest_sum_of_trade", "closest_score", "highest_rap_gain", 
                "lowest_rap_gain", "highest_algo_gain", "lowest_algo_gain", 
                "highest_value_gain", "lowest_value_gain", "upgrade", "downgrade"
            ]
            print("\nSelect one of the following options:")
            for i, option in enumerate(options, 1):
                print(f"{i}. {option}")

            try:
                choice = int(input(f"Enter your choice (current: {current_value}): "))
                if 1 <= choice <= len(options):
                    data_config[key] = options[choice - 1]
                    print(f"{key} updated to {data_config[key]}.")
                else:
                    print("Invalid choice. Keeping current value.")
            except ValueError:
                print("Invalid input. Keeping current value.")
        else:
            new_value = input(f"Enter new value for {key} (current: {current_value}): ").strip()
            if new_value:
                try:
                    data_config[key] = self.convert_value_type(new_value, type(current_value))
                    print(f"{key} updated to {data_config[key]}.")
                except ValueError:
                    print("Invalid input type. Keeping current value.")
            else:
                print(f"Keeping current value for {key}: {current_value}")

    def convert_value_type(self, value, expected_type):
        """Convert input value to the expected type."""
        if expected_type is int:
            return int(value)
        elif expected_type is float:
            return float(value)
        return value

