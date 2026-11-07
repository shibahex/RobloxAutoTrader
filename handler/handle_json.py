import json
import threading
import os
import handler.handle_cli as handle_cli

# import handler.handle_cli
import time
from datetime import datetime, timedelta
from handler.handle_logs import log
from handler.exceptions_types import DataFileError

TRADE_LIMIT = "hit the trade limit"
PAUSE_HOURS = 6


def pause_until(account: dict) -> datetime | None:
    """When the account can send trades again, or None if it isn't paused."""
    stamp = account.get("ratelimit_timestamp")
    if not stamp:
        return None
    try:
        until = datetime.fromisoformat(stamp) + timedelta(
            hours=float(account.get("ratelimit_hours") or PAUSE_HOURS)
        )
    except (TypeError, ValueError):
        log(f"[FILES] Bad trade limit time {stamp!r}, ignoring it", dontPrint=True)
        return None
    return until if until > datetime.now() else None


def clock(when: datetime) -> str:
    """'7:12 PM', or 'Fri 7:12 PM' when it isn't today."""
    text = when.strftime("%I:%M %p").lstrip("0")
    return text if when.date() == datetime.now().date() else when.strftime("%a ") + text


class JsonHandler:
    # filename -> ((mtime_ns, size), data): shared read-only snapshots
    _snapshots: dict = {}
    _snapshots_lock = threading.Lock()

    def __init__(self, filename):
        self.filename = filename
        # RLock so read_data can call write_data while holding it
        self.lock = threading.RLock()
        self.cli = handle_cli.Terminal()
        if self.filename == "cookies.json" and not os.path.exists(self.filename):
            initial_data = {"roblox_accounts": []}
            self.write_data(initial_data)

        if not os.path.exists(self.filename):
            log("File doenst exist generating empty json.")
            self.write_data({})
            # Hide it
            if self.filename[0] == "." and os.name == "nt":
                os.system(f"attrib +h +s {self.filename}")  # Hide the file

    def _empty_data(self) -> dict:
        if self.filename == "cookies.json":
            return {"roblox_accounts": []}
        return {}

    def read_cached(self) -> dict:
        """
        Read-only snapshot of the file, kept in memory and re-read only when the
        file changes on disk. Much faster for hot paths (pricing reads the
        projected data hundreds of times a minute). Never modify what this
        returns: use read_data() + write_data() to change the file.
        """
        try:
            stat = os.stat(self.filename)
        except OSError:
            return self.read_data()
        version = (stat.st_mtime_ns, stat.st_size)
        cached = JsonHandler._snapshots.get(self.filename)
        if cached and cached[0] == version:
            return cached[1]
        data = self.read_data()
        with JsonHandler._snapshots_lock:
            JsonHandler._snapshots[self.filename] = (version, data)
        return data

    def read_data(self) -> dict:
        """
        Reads data from the JSON file.
        A corrupt file is backed up next to the original and replaced with empty data.
        Raises DataFileError if the file can't be read at all (permissions, disk).
        """
        with self.lock:
            try:
                if self.filename[0] == "." and os.name == "nt":
                    os.system(f"attrib -h -s {self.filename}")
                with open(self.filename, "r", encoding="utf-8") as file:
                    return json.load(file)
            except FileNotFoundError:
                log(f"[FILES] {self.filename} is missing, creating an empty one", severityNum=2)
                initial_data = self._empty_data()
                self.write_data(initial_data)
                return initial_data
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                backup = f"{self.filename}.corrupt-{int(time.time())}"
                try:
                    os.replace(self.filename, backup)
                except OSError as move_error:
                    raise DataFileError(
                        f"{self.filename} is corrupt ({e}) and couldn't be backed up: {move_error}"
                    ) from e
                log(
                    f"[FILES] {self.filename} was corrupt ({e}). Backed it up to {backup} and started fresh.",
                    severityNum=4,
                )
                initial_data = self._empty_data()
                self.write_data(initial_data)
                return initial_data
            except OSError as e:
                raise DataFileError(f"Couldn't read {self.filename}: {e}") from e
            finally:
                if self.filename[0] == "." and os.name == "nt":
                    os.system(f"attrib +h +s {self.filename}")

    def write_data(self, data: dict) -> None:
        """Safely Writes data to the JSON file."""
        with JsonHandler._snapshots_lock:
            JsonHandler._snapshots.pop(self.filename, None)
        temp_file = self.filename + ".tmp"  # Temporary file for atomic writing

        # Unhide the file if needed (Windows)
        if self.filename[0] == "." and os.name == "nt":
            os.system(f'attrib -h -s "{self.filename}"')
            os.system(f'attrib -h -s "{temp_file}"')

        try:
            with self.lock:
                with open(temp_file, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=4)
                    file.flush()
                    # Ensure data is written to disk
                    os.fsync(file.fileno())
                os.replace(temp_file, self.filename)
        except (OSError, TypeError, ValueError) as e:
            # TypeError/ValueError: data isn't JSON serializable
            raise DataFileError(f"Couldn't write {self.filename}: {e}") from e
        finally:
            # Re-hide the file if needed (Windows)
            if self.filename[0] == "." and os.name == "nt":
                os.system(f'attrib +h +s "{self.filename}"')

    def add_ratelimit_timestamp(self, cookie, reason=TRADE_LIMIT, hours=None) -> None:
        """
        Pauses an account: it won't send trades until the time is up.
        reason says why (shown in the console), hours how long (default 6).
        """
        data = self.read_data()
        for account in data["roblox_accounts"]:
            if account.get("cookie") == cookie:
                account["ratelimit_timestamp"] = datetime.now().isoformat()
                account["ratelimit_reason"] = reason
                account["ratelimit_hours"] = hours or PAUSE_HOURS
                self.write_data(data)
                return True

    def return_name_from_id(self, user_id):
        data = self.read_data()

        for account in data["roblox_accounts"]:
            if str(account.get("user_id")) == str(user_id):
                return account.get("username")

        return "Couldn't find username."

    def return_userid_from_index(self, index: int, check_config=False):
        index = int(index) - 1
        data = self.read_data()

        # Filter accounts based on `check_config`
        if check_config:
            with open("account_configs.jsonc", "r") as file:
                settings_data = json.load(file)
            filtered_accounts = [
                account
                for account in data["roblox_accounts"]
                if account["user_id"] not in settings_data.keys()
            ]
        else:
            filtered_accounts = data["roblox_accounts"]

        # Check if the index is within bounds for the filtered list
        if 0 <= index < len(filtered_accounts):
            return filtered_accounts[index].get("user_id", False)
        return False

    def toggle_cookie(self, index: int) -> None:
        data = self.read_data()
        if 0 <= index < len(data["roblox_accounts"]):
            toggle = data["roblox_accounts"][index]["use_account"]

            data["roblox_accounts"][index]["use_account"] = not toggle

            self.write_data(data)
            self.cli.print_success(f"Cookie toggled to {not toggle}")
            time.sleep(1)
        else:
            self.cli.print_error("Invalid index. No cookie deleted.")

    def is_disabled(self, cookie):
        data = self.read_data()
        for account in data["roblox_accounts"]:
            if account.get("cookie") == cookie:
                return account["use_account"]

        # for some reason if theres no use account value
        return False

    def is_all_ratelimited(self) -> bool:
        """True when every account that's ON is paused (and at least one is ON)."""
        accounts = [a for a in self.read_data()["roblox_accounts"] if a.get("use_account")]
        return bool(accounts) and all(pause_until(a) for a in accounts)

    def paused_text(self) -> str:
        """One line per paused account: who, why, and until when."""
        lines = []
        for account in self.read_data()["roblox_accounts"]:
            until = pause_until(account) if account.get("use_account") else None
            if until:
                lines.append(
                    f"{account.get('username')}: {account.get('ratelimit_reason') or TRADE_LIMIT}, "
                    f"until {clock(until)}"
                )
        return "\n".join(lines)

    def update_last_completed(self, cookie, last_completed: int or str) -> None:
        data = self.read_data()
        for account in data["roblox_accounts"]:
            if (
                account.get("cookie") == cookie
                and account.get("last_completed") != last_completed
            ):
                account["last_completed"] = last_completed
                self.write_data(data)
                return True

    def get_last_completed(self, cookie) -> str or None:
        data = self.read_data()
        for account in data["roblox_accounts"]:
            if account.get("cookie") == cookie:
                return account.get("last_completed")

    def check_ratelimit_cookie(self, cookie) -> bool:
        """True while the account is paused (trade limit, no items...)."""
        for account in self.read_data()["roblox_accounts"]:
            if account.get("cookie") == cookie:
                return pause_until(account) is not None
        return False

    def add_cookie(self, cookie, username, user_id, auth) -> None:
        data = self.read_data()

        # Check for duplicate cookies
        if not any(account["cookie"] == cookie for account in data["roblox_accounts"]):
            data["roblox_accounts"].append(
                {
                    "username": username,
                    "user_id": user_id,
                    "use_account": True,
                    "last_completed": None,
                    "cookie": cookie,
                    "auth_secret": auth,
                    "ratelimit_timestamp": None,
                }
            )

            self.write_data(data)
            self.cli.print_success("Cookie added suscessfully")
            time.sleep(1)
        else:
            print("Cookie already exists.")
            time.sleep(1)

    def set_rolimons_cookie(self, index: int, rolimons_cookie) -> bool:
        """Saves (or with None, removes) an account's Rolimons cookie."""
        data = self.read_data()
        accounts = data["roblox_accounts"]
        if not 0 <= index < len(accounts):
            self.cli.print_error("Invalid number.")
            return False
        if rolimons_cookie:
            accounts[index]["rolimons_cookie"] = rolimons_cookie
        else:
            accounts[index].pop("rolimons_cookie", None)
        self.write_data(data)
        return True

    def delete_cookie(self, index: int) -> None:
        data = self.read_data()
        if 0 <= index < len(data["roblox_accounts"]):
            del data["roblox_accounts"][index]
            self.write_data(data)
            self.cli.print_success("Cookie deleted successfully.")
            time.sleep(1)
        else:
            self.cli.print_error("Invalid index. No cookie deleted.")

    def list_cookies(self, check_config=False) -> None:
        def ordinal(num):
            special_ordinals = {1: "first", 2: "second", 3: "third"}
            if num in special_ordinals:
                return special_ordinals[num]

            if 10 <= num % 100 <= 20:
                suffix = "th"
            else:
                suffixes = {1: "st", 2: "nd", 3: "rd"}
                suffix = suffixes.get(num % 10, "th")
            return f"{num}{suffix}"

        data = self.read_data()
        cookie_count = 0
        if data["roblox_accounts"]:
            for account in data["roblox_accounts"]:
                if check_config:
                    with open("account_configs.jsonc", "r") as file:
                        settings_data = json.load(file)
                    if account["user_id"] in settings_data.keys():
                        continue

                cookie_count += 1
                title = f"{handle_cli.magenta}[{
                    handle_cli.reset + str(cookie_count) + handle_cli.magenta
                }] {ordinal(cookie_count)} cookie{handle_cli.reset}"

                shorten_cookie = account["cookie"][: len(account["cookie"]) // 6]
                cookie_info = f"\nusername: {account['username']},\n user id: {
                    account['user_id']
                }\nratelimited: {account['ratelimit_timestamp']}\nrolimons cookie: {
                    'set' if account.get('rolimons_cookie') else 'not set'
                }\nenabled: {account['use_account']}\n\nshortened cookie: {
                    shorten_cookie
                }\nauth secret: {account['auth_secret']}\n"

                print("---" + title + "---" + cookie_info)

        else:
            print("no cookies found.")

    def update_missing_config(self, default_trading_config: dict) -> None:
        # List all cookies
        acc_configs = JsonHandler("account_configs.jsonc")
        data = acc_configs.read_data()

        default_keys = default_trading_config.keys()
        for user_config in data:
            # Convert to list for safe iteration
            inventory_keys = list(data[user_config].keys())

            # Add missing keys
            for key in default_keys:
                if key not in inventory_keys:
                    data[user_config][key] = default_trading_config[key]
                    print(f"Added missing key {key} to {user_config}")

            # Remove extra keys
            for key in inventory_keys:
                if key not in default_keys:
                    del data[user_config][key]
                    print(f"Removed key {key} from {user_config}")

        acc_configs.write_data(data)
        print("Configurations updated with missing keys.")
        time.sleep(3)

    def update_projected_status(
        self, item_id: int or str, projected_status: bool, current_price: int or str
    ) -> None:
        """Updates the projected status of a specific item ID."""
        data = self.read_data()
        now_time = datetime.now()

        data[item_id] = {
            "is_projected": projected_status,
            "timestamp": now_time.timestamp(),
            "last_price": current_price,
        }
        self.write_data(data)
