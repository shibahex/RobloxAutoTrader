from handler.handle_json import JsonHandler
from handler.handle_config import ConfigHandler
from handler.handle_logs import log
import configparser
import os
import time


NONE_WORDS = {"none", "null"}
UNSET = (None, "Not Set")


def parse_config_value(text: str):
    """
    Turns what the user typed into a Python value:
    "None" -> None, "true"/"false" -> bool, "100" -> 100, "0.5" -> 0.5,
    anything else stays a string.
    """
    cleaned = str(text).strip()
    lowered = cleaned.lower()
    if lowered in NONE_WORDS:
        return None
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return cleaned


def coerce_config_value(value, expected_type, text=None):
    """
    Checks a parsed value against the type the setting needs.
    Whole-number settings need a whole number; decimal settings take either
    (gains like 0.1 are percentages). None is allowed for number settings (means "no limit"), not for true/false
    or text settings. Raises ValueError with a readable reason.
    """
    if expected_type is None:
        return value
    if expected_type is bool:
        if isinstance(value, bool):
            return value
        raise ValueError("expected true or false")
    if expected_type in (int, float):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("expected a number or None")
        if expected_type is int:
            if isinstance(value, float) and not value.is_integer():
                raise ValueError("expected a whole number or None")
            return int(value)
        return value
    if expected_type is str:
        if value is None:
            raise ValueError("this setting can't be None")
        return str(text if text is not None else value)
    return value


class HandleConfigs:
    def __init__(self):
        self.acc_configs = JsonHandler("account_configs.jsonc")
        self.cookies = JsonHandler("cookies.json")
        self.default_config = ConfigHandler().trading

    def expected_type(self, key, current_value=None):
        """
        The type a setting should have: from the main config's default if it's
        set, otherwise from the saved value. None means "anything goes".
        """
        default = self.default_config.get(key)
        for candidate in (default, current_value):
            if candidate not in UNSET:
                return type(candidate)
        return None

    def get_config(self, user_id):
        """
        Retrieve the configuration for a specific user ID.
        Repairs values saved as text by older versions (e.g. "100" -> 100).
        """
        data = self.acc_configs.read_data()
        config = dict(data.get(user_id, {}))
        for key, value in config.items():
            if not isinstance(value, str):
                continue
            expected = self.expected_type(key)
            if expected is str:
                continue
            if expected is None:
                # No known type: still undo "None"/"100"/"true" saved as text
                config[key] = parse_config_value(value)
                continue
            try:
                config[key] = coerce_config_value(parse_config_value(value), expected)
            except ValueError:
                log(
                    f"Account config {key} = {value!r} isn't a valid {expected.__name__}"
                )
        return config

    def check_for_updates(self):
        self.acc_configs.update_missing_config(self.default_config)

    def select_user_id(self):
        """Prompt the user to select a user ID from available keys."""
        # TODO: add option to reset a config to default
        data = self.acc_configs.read_data()
        user_ids = list(data.keys())
        if not user_ids:
            log("no user configurations found.")
            return False

        log("\nSelect a user ID to configure:")
        for i, user_id in enumerate(user_ids, 1):
            log(f"{i}. {user_id}:  {self.cookies.return_name_from_id(str(user_id))}")

        try:
            choice = int(input("\nEnter the number of the user ID: "))
            if choice < 1 or choice > len(user_ids):
                raise ValueError
            return user_ids[choice - 1]
        except ValueError:
            log("Invalid input. Exiting.")
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
                except (configparser.Error, OSError, UnicodeDecodeError) as e:
                    log(f"Couldn't read config {file}: {e}")
                    continue

                if "Info" in config and "Description" in config["Info"]:
                    log(f"({enum + 1}) {file} | {config['Info']['Description']}")
                else:
                    log(f"({enum + 1}) {file} | Config doesnt have description")

        try:
            chosen = (
                int(input("\nPlease Enter the Number of the Config you want to use > "))
                - 1
            )
            if 0 <= chosen < len(file_names):
                chosen_config = file_names[chosen]
                with open(f"{directory}/{chosen_config}", "r") as f:
                    config_contents = f.read()

                with open("./config.cfg", "w") as f:
                    f.write(config_contents)

                log(
                    f"\nReplaced './config.cfg' with the contents of '{file_names[chosen]}'"
                )
                time.sleep(1)
            else:
                log("Invalid Choice")
                time.sleep(3)
        except ValueError:
            log("Invalid Choice, enter a number")
            time.sleep(3)
        except OSError as e:
            log(f"Couldn't copy the preset into config.cfg: {e}", severityNum=3)
            time.sleep(3)

    def show_config(self, user_id=None):
        """List grouped and single keys in a user's configuration."""
        if user_id is None:
            user_id = self.select_user_id()
        if not user_id:
            return {}, []

        data_config = self.get_config(user_id)
        if not data_config:
            log(f"No configuration found for user ID {user_id}.")
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

        log("\nConfigurations:")
        for i, (name, (min_key, max_key)) in enumerate(grouped_keys.items(), 1):
            log(
                f"{i}. {name}: Min = {data_config[min_key]}, Max = {data_config[max_key]}"
            )
        for j, key in enumerate(single_keys, len(grouped_keys) + 1):
            log(f"{j}. {key}: {data_config[key]}")

        return grouped_keys, single_keys

    def create_config(self):
        json_handler = JsonHandler("cookies.json")

        json_handler.list_cookies(check_config=True)
        index = input("Enter number to create config from (Press enter to quit): ")
        if index is None or index == "":
            return

        user_id = json_handler.return_userid_from_index(index, check_config=True)

        if not user_id:
            log("Couldnt find userid")
            time.sleep(3)
            return

        data = self.acc_configs.read_data()
        data[user_id] = self.default_config
        self.acc_configs.write_data(data)

    def delete_config(self, user_id=None):
        if user_id is None:
            user_id = self.select_user_id()
            if not user_id:
                # Do nothing if they pressed enter
                return
        data = self.acc_configs.read_data()
        if user_id not in data:
            log(f"No config saved for {user_id}")
            return
        del data[user_id]
        self.acc_configs.write_data(data)

    def edit_config(self):
        """Edit a user's configuration interactively until they quit."""
        user_id = self.select_user_id()
        if not user_id:
            return
        while True:
            data_config = self.get_config(user_id)
            if not data_config:
                log(f"No configuration found for user ID {user_id}.")
                return

            grouped_keys, single_keys = self.show_config(user_id)

            options = list(grouped_keys.keys()) + single_keys

            try:
                choice_input = input(
                    "\nEnter the number of the configuration to edit (or type 'quit' to exit): "
                )
                if choice_input.strip().lower() == "quit" or not choice_input.strip():
                    log("Exiting the configuration editor.")
                    break

                choice = int(choice_input)
                if choice < 1 or choice > len(options):
                    raise ValueError
            except ValueError:
                log("Invalid input. Please try again.")
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
            log("Data successfully written to account_configs.jsonc.")

    def prompt_and_update(self, data_config, key):
        """Prompt the user to update a configuration value."""
        current_value = data_config[key]

        if key == "Select_Trade_Using":
            # Exactly what the trade picker supports
            from trade_algorithm import SELECT_TRADE_OPTIONS

            options = list(SELECT_TRADE_OPTIONS)
            log("\nSelect one of the following options:")
            for i, option in enumerate(options, 1):
                log(f"{i}. {option}")

            try:
                choice = int(input(f"Enter your choice (current: {current_value}): "))
                if 1 <= choice <= len(options):
                    data_config[key] = options[choice - 1]
                    log(f"{key} updated to {data_config[key]}.")
                else:
                    log("Invalid choice. Keeping current value.")
            except ValueError:
                log("Invalid input. Keeping current value.")
        else:
            expected = self.expected_type(key, current_value)
            hint = {
                bool: "true/false",
                int: "a whole number, or None for no limit",
                float: "a number, or None for no limit",
                str: "text",
            }.get(expected, "a value, or None")
            new_value = input(
                f"Enter new value for {key} [{hint}] (current: {current_value}): "
            ).strip()
            if not new_value:
                log(f"Keeping current value for {key}: {current_value}")
                return
            try:
                data_config[key] = coerce_config_value(
                    parse_config_value(new_value), expected, text=new_value
                )
                log(f"{key} updated to {data_config[key]!r}.")
            except ValueError as e:
                log(f"Invalid value for {key} ({e}). Keeping current value.")
