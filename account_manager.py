from roblox_api import RobloxAPI
from handler.handle_json import JsonHandler
from handler.handle_cli import Terminal
from handler.handle_2fa import AuthHandler
from handler.handle_login import FirefoxLogin
from handler.exceptions_types import (
    TradebotError,
    CookieInvalid,
)

COOKIE_WARNING = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|"

COOKIE_DISCLAIMER = (
    "Your .ROBLOSECURITY cookie logs in as you. Giving it to the bot hands it\n"
    "your account so it can trade for you. It's saved in cookies.json on this\n"
    "computer only. Never share it with anyone else."
)


def cookie_candidates(raw: str) -> list:
    """
    The cookie forms to try logging in with, best first. Accepts the cookie
    with or without Roblox's "_|WARNING:...|_" text, and also a pasted
    ".ROBLOSECURITY=" prefix, quotes or spaces. Empty input gives [].
    """
    cookie = (raw or "").strip()
    if cookie.lower().startswith(".roblosecurity="):
        cookie = cookie.split("=", 1)[1]
    cookie = cookie.strip().rstrip(";").strip().strip("'\"").strip()
    if not cookie:
        return []
    if cookie.startswith("_|WARNING:"):
        return [cookie]
    # Roblox's own cookie starts with the warning text; try that first, then
    # exactly what was pasted
    return [COOKIE_WARNING + "_" + cookie, cookie]


class AccountManager:
    def __init__(self):
        self.json_handler = JsonHandler("cookies.json")
        self.cli = Terminal()
        pass

    def main(self):
        while True:
            self.cli.clear_console()
            options = (
                ("1", "Add Account (Firefox Required)"),
                ("2", "Add Account (Manual)"),
                ("3", "Remove Accounts"),
                ("4", "Toggle Accounts"),
                ("5", "Back to Main Menu"),
            )
            self.cli.print_menu("Account Manager", options)
            try:
                answer = int(self.cli.input_prompt("Enter Option"))
            except ValueError:
                self.cli.print_error("Invalid input. Please enter a number.")
                continue

            match answer:
                case 1:
                    self.add_account()
                case 2:
                    self.manually_add_account()
                case 3:
                    self.remove_accounts()
                case 4:
                    self.toggle_accounts()
                case 5:
                    break

    def toggle_accounts(self):
        while True:
            self.cli.clear_console()
            self.json_handler.list_cookies()
            try:
                index = self.cli.input_prompt(
                    "Enter the number of the cookie to toggle (Press enter to stop)"
                )
                self.json_handler.toggle_cookie(int(index) - 1)
            except ValueError:
                if index.lower() == " " or index.lower() == "":
                    break

                self.cli.print_error(f"Invalid input: '{index}' is not a valid number.")
            except TradebotError as e:
                self.cli.print_error(f"Couldn't update cookies.json: {e}")
                break

    def remove_accounts(self):
        while True:
            self.cli.clear_console()
            self.json_handler.list_cookies()
            try:
                index = self.cli.input_prompt(
                    "Enter the number of the cookie to delete (Press enter to stop)"
                )
                self.json_handler.delete_cookie(int(index) - 1)
            except ValueError:
                if index.lower() == " " or index.lower() == "":
                    break
                self.cli.print_error(f"Invalid input: '{index}' is not a valid number.")
            except TradebotError as e:
                self.cli.print_error(f"Couldn't update cookies.json: {e}")
                break

    def manually_add_account(self):
        auth_secret = self.cli.input_prompt("Enter 2FA Secret Code")

        if not AuthHandler().verify_auth_secret(auth_secret):
            self.cli.print_error(
                "That 2FA Secret Code isn't valid, skipping account..."
            )
            return None

        print(f"\n{COOKIE_DISCLAIMER}\n")
        candidates = cookie_candidates(
            self.cli.input_prompt(
                "Enter .ROBLOSECURITY Cookie (with or without the warning)"
            )
        )
        if not candidates:
            self.cli.print_error("No cookie entered, skipping account...")
            return None

        roblox_login = acc_cookie = None
        for acc_cookie in candidates:
            try:
                roblox_login = RobloxAPI(
                    cookie={".ROBLOSECURITY": acc_cookie}, auth_secret=auth_secret
                )
                break
            except CookieInvalid:
                continue
            except TradebotError as error:
                self.cli.print_error(f"{error}\nSkipping account...")
                return None
        if roblox_login is None:
            self.cli.print_error(
                "That cookie is expired or invalid.\nSkipping account..."
            )
            return None

        self.json_handler.add_cookie(
            acc_cookie, roblox_login.username, roblox_login.account_id, auth_secret
        )

    def add_account(self):
        auth_secret = self.cli.input_prompt("Enter 2FA Secret Code")

        if not AuthHandler().verify_auth_secret(auth_secret):
            self.cli.print_error(
                "That 2FA Secret Code isn't valid, skipping account..."
            )
            return None

        print(f"\n{COOKIE_DISCLAIMER}\n")
        firefox = FirefoxLogin()

        try:
            cookie, username, user_id = firefox.roblox_login(auth_secret)
            firefox.stop()
        except ValueError as e:
            self.cli.print_error(f"{e}\nSkipping account...")
            firefox.stop()
            return None
        self.json_handler.add_cookie(cookie, username, user_id, auth_secret)
