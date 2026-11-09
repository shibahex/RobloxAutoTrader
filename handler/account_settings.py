from handler.handle_json import JsonHandler
from handler.handle_config import ConfigHandler
from handler.handle_logs import log
import configparser
import os
import re
import shutil
import time


NONE_WORDS = {"none", "null"}
# Settings that do nothing, so they aren't copied into config.cfg
UNUSED_OPTIONS = {"RobuxDividePercentage"}
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


def config_text(key, value) -> str:
    """An account config value as config.cfg writes it."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def set_options(text: str, values: dict) -> tuple[str, list]:
    """
    Sets options in config.cfg's text, keeping its comments and layout.
    values: {(section, option): new text}. An option that isn't there is added
    at the end of its section. Returns (new text, [(section, option, old, new)]
    for every option that changed).
    """
    lines = text.split("\n")
    changes = []
    for (section, option), new in values.items():
        start = next(
            (i for i, line in enumerate(lines)
             if line.strip().lower() == f"[{section.lower()}]"),
            None,
        )
        if start is None:
            continue
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
            len(lines),
        )
        pattern = re.compile(rf"^\s*{re.escape(option)}\s*[=:]\s*(.*)$", re.I)
        for i in range(start + 1, end):
            match = pattern.match(lines[i])
            if match:
                old = match.group(1).strip()
                # Same meaning written differently (true/True, 450/450.0): keep it
                if parse_config_value(old) != parse_config_value(new):
                    lines[i] = f"{option} = {new}"
                    changes.append((section, option, old, new))
                break
        else:
            last = end - 1
            # Skip blank lines and the next section's "# ====" banner
            while last > start and (
                not lines[last].strip() or re.fullmatch(r"#\s*=+\s*", lines[last].strip())
            ):
                last -= 1
            lines.insert(last + 1, f"{option} = {new}")
            changes.append((section, option, None, new))
    return "\n".join(lines), changes


def written_names(text: str, values: dict) -> dict:
    """
    values keyed by the old (section, option) names, renamed to the new ones
    when config.cfg uses the new layout ([Profit], [Trade Rules]...).
    """
    from handler.handle_config import LAYOUT

    headers = {line.strip().lower() for line in text.split("\n") if line.strip().startswith("[")}
    renamed = {}
    for (section, option), value in values.items():
        new = LAYOUT.get((section, option))
        if new and f"[{new[0].lower()}]" in headers:
            renamed[new] = value
        else:
            renamed[(section, option)] = value
    return renamed


# Account settings: key -> (ConfigHandler dict it overrides, section, option)
ACCOUNT_OPTIONS = {
    key: (attr, section, option)
    for attr, table in (
        ("trading", ConfigHandler.TRADING_OPTIONS),
        ("filter_items", ConfigHandler.ITEMS_OPTIONS),
        ("filter_generated", ConfigHandler.PICKING_OPTIONS),
    )
    for key, (section, option) in table.items()
    if key not in UNUSED_OPTIONS
}
# Settings that are a list of item IDs
LIST_OPTIONS = {"NFT", "NFR"}


def shown_name(key) -> tuple[str, str]:
    """(section, option) of an account setting, as config.cfg writes it now."""
    from handler.handle_config import LAYOUT

    _, section, option = ACCOUNT_OPTIONS[key]
    return LAYOUT.get((section, option), (section, option))


def choices(key) -> list | None:
    """The allowed values of a pick-one setting, or None."""
    if key == "Rap_Algo_For_Valued":
        return ["rap_algo", "rolimon_value", "zero_value"]
    return None


def shown_value(key, value) -> str:
    if key in LIST_OPTIONS:
        return ", ".join(map(str, value)) if value else "None"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class HandleConfigs:
    """
    Per-account settings in account_configs.jsonc. An account config only
    holds the settings that differ from config.cfg; the rest come from it.
    """

    def __init__(self, config_file="config.cfg"):
        self.acc_configs = JsonHandler("account_configs.jsonc")
        self.cookies = JsonHandler("cookies.json")
        main = ConfigHandler(config_file)
        self.main_values = {
            key: getattr(main, attr)[key] for key, (attr, _, _) in ACCOUNT_OPTIONS.items()
        }
        # Older code and tests call it this
        self.default_config = self.main_values

    def expected_type(self, key, current_value=None):
        """The type a setting should have (from config.cfg, else the saved value)."""
        for candidate in (self.main_values.get(key), current_value):
            if candidate not in UNSET:
                return type(candidate)
        return None

    def get_config(self, user_id) -> dict:
        """
        An account's own settings. Repairs values saved as text by older
        versions (e.g. "100" -> 100).
        """
        config = dict(self.acc_configs.read_data().get(str(user_id), {}))
        for key, value in config.items():
            if not isinstance(value, str) or key in LIST_OPTIONS:
                continue
            expected = self.expected_type(key)
            if expected is str:
                continue
            if expected is None:
                config[key] = parse_config_value(value)
                continue
            try:
                config[key] = coerce_config_value(parse_config_value(value), expected)
            except ValueError:
                log(f"Account config {key} = {value!r} isn't a valid {expected.__name__}")
        return config

    def apply(self, config, user_id) -> bool:
        """
        Puts an account's own settings over config.cfg's in config (a
        ConfigHandler). Returns True if the account has any.
        """
        settings = self.get_config(user_id)
        for key, value in settings.items():
            attr = ACCOUNT_OPTIONS.get(key, ("trading",))[0]
            getattr(config, attr)[key] = value
        return bool(settings)

    def set_value(self, user_id, key, value):
        data = self.acc_configs.read_data()
        data.setdefault(str(user_id), {})[key] = value
        self.acc_configs.write_data(data)

    def reset_value(self, user_id, key):
        """Back to the config.cfg value."""
        data = self.acc_configs.read_data()
        data.get(str(user_id), {}).pop(key, None)
        if str(user_id) in data and not data[str(user_id)]:
            del data[str(user_id)]
        self.acc_configs.write_data(data)

    def delete_config(self, user_id):
        """Removes all of an account's own settings."""
        data = self.acc_configs.read_data()
        if data.pop(str(user_id), None) is not None:
            self.acc_configs.write_data(data)

    def parse(self, key, text: str):
        """
        What the user typed, as the setting's value. Raises ValueError with a
        readable reason.
        """
        if key in LIST_OPTIONS:
            from handler.handle_config import _item_ids

            parts = [p.strip() for p in text.split(",") if p.strip()]
            if len(parts) == 1 and parts[0].lower() in NONE_WORDS:
                return []
            ids = _item_ids(parts)
            if not all(i.isdigit() for i in ids):
                raise ValueError("expected item IDs separated by commas")
            return ids
        if key == "Select_Trade_Using":
            from trade_algorithm import is_blend, parse_pick

            parse_pick(text)  # ValueError names the unknown option
            if is_blend(text):
                names, _ = parse_pick(text)
                return "blend: " + ", ".join(names)
            return " + ".join(part.strip().lower() for part in text.split("+") if part.strip())
        options = choices(key)
        if options:
            wanted = text.strip().lower()
            for option in options:
                if wanted in (option.lower(), shown_value(key, option).lower()):
                    return option
            raise ValueError("must be one of: " + ", ".join(shown_value(key, o) for o in options))
        expected = self.expected_type(key)
        return coerce_config_value(parse_config_value(text), expected, text=text)

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

    def apply_to_main(self, user_id, path="config.cfg", ask=input):
        """
        Writes an account's settings into config.cfg (backing it up first as
        config.backup.cfg), then offers to remove the account's config so it
        uses config.cfg from now on.
        """
        account = self.get_config(user_id)
        name = self.cookies.return_name_from_id(str(user_id)) or user_id
        values = {}
        for key, value in account.items():
            if key not in ACCOUNT_OPTIONS:
                continue
            if value is None and isinstance(self.main_values.get(key), bool):
                value = False  # old account configs saved unset switches as None
            _, section, option = ACCOUNT_OPTIONS[key]
            text = shown_value(key, value) if key in LIST_OPTIONS else config_text(key, value)
            values[(section, option)] = text
        unknown = [k for k in account if k not in ACCOUNT_OPTIONS and k not in UNUSED_OPTIONS]

        with open(path, encoding="utf-8") as f:
            text = f.read()
        values = written_names(text, values)
        new_text, changes = set_options(text, values)
        if not changes:
            print(f"config.cfg already has {name}'s settings.")
        else:
            print(f"\nThese config.cfg settings change to {name}'s:")
            for number, (section, option, old, new) in enumerate(changes, 1):
                print(f"  {number}. [{section}] {option}: {old if old is not None else '(missing)'} -> {new}")
        if unknown:
            print(f"Not in config.cfg, skipped: {', '.join(unknown)}")
        if changes:
            skip = self.ask_skip(changes, ask)
            if skip:
                kept = {(s, o): new for s, o, _, new in changes if (s, o) not in skip}
                new_text, changes = set_options(text, kept)
                if not changes:
                    print("Every change skipped, config.cfg stays the same.")
            if changes:
                print("Writing:")
                for section, option, old, new in changes:
                    print(f"  [{section}] {option}: {old if old is not None else '(missing)'} -> {new}")
                if ask("\nWrite these into config.cfg? (y/n): ").strip().lower() != "y":
                    print("Nothing changed.")
                    return False
                shutil.copyfile(path, "config.backup.cfg")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_text)
                print("Saved config.cfg (the old one is in config.backup.cfg).")

        if ask(f"Remove {name}'s account config so it uses config.cfg? (y/n): ").strip().lower() == "y":
            self.delete_config(user_id)
            print(f"Removed {name}'s account config.")
        return True

    @staticmethod
    def ask_skip(changes, ask=input) -> set:
        """
        Asks which changes to leave out, by number ("2,5" or "2 5"). Returns
        their (section, option). Enter = skip none.
        """
        while True:
            answer = ask(
                "\nNumbers of settings NOT to apply (e.g. 2,5), or press enter to apply all: "
            ).strip()
            if not answer:
                return set()
            try:
                numbers = {int(n) for n in re.split(r"[\s,]+", answer) if n}
            except ValueError:
                print("Enter numbers like 2,5")
                continue
            if not all(1 <= n <= len(changes) for n in numbers):
                print(f"Numbers go from 1 to {len(changes)}")
                continue
            return {(changes[n - 1][0], changes[n - 1][1]) for n in numbers}
