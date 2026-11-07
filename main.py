# Must run first: fixes for the packaged build (see handler/startup.py)
import handler.startup  # noqa: F401
import re
import time
import traceback
from rolimons_api import RolimonAPI
from roblox_api import RobloxAPI
import threading
from handler.handle_json import JsonHandler
from account_manager import AccountManager
import config_manager
from handler.account_settings import HandleConfigs
import sys
from handler.handle_logs import log
from handler.handle_cli import Terminal
from handler.handle_discord import DiscordHandler
from handler import exceptions_types
from handler.handle_trade_ads import TradeAdPoster
from version import full_version
from handler import update_check


"""
    Ideas not done yet:
    - if an account has no valued items, switch it to rap_config.cfg
    - scan owners' inventories on more than one thread
    - post Rolimons / Discord trade ads to get more inbounds to counter
    - don't keep countering trades from the same person
"""


class Doggo:
    def __init__(self):
        """
        Store all the variables that will be used across doggo class
        """
        self.user_queue = {}
        self.cli = Terminal()
        self.json = JsonHandler(filename="cookies.json")
        self.rolimons = RolimonAPI()

        self.account_configs = HandleConfigs()
        self.discord_webhook = DiscordHandler()

        # Define a stop event that will be shared between threads
        self.stop_event = threading.Event()

        # Accounts turned off this session (expired cookie, etc.), by id()
        self.disabled_accounts = set()

        # Time Stamps for Routines
        self.last_updated_rolimons = time.time()
        self.last_checked_trades = time.time()

    def main(self):
        """
        A loop that runs the Menu and clears the console
        """
        update_check.check_in_background()
        while True:
            self.cli.clear_console()
            self.display_main_menu()

    def display_main_menu(self):
        """
        CLI Menu that has a bunch of options and handles the selected answer
        """
        options = (
            (1, "Account Manager"),
            (2, "Config Manager"),
            (3, "Execute Trader"),
        )
        log(f"[BOT] Version {full_version()}")
        update_check.wait(3)
        if update_check.message:
            log(update_check.message, severityNum=1)
        self.cli.print_menu("Main Menu", options)
        try:
            answer = int(self.cli.input_prompt("Enter Option"))
        except ValueError:
            self.cli.print_error("Invalid input. Please enter a number.")
            return

        try:
            self.handle_menu_selection(answer)
        except exceptions_types.TradebotError as e:
            self.cli.print_error(f"{type(e).__name__}: {e}")
            input("Press enter to go back to the menu.")

    def handle_menu_selection(self, selection):
        """
        Matches Selection to the function
        """
        match selection:
            case 1:
                AccountManager().main()
            case 2:
                # Trade Manager functionality can be implemented here
                config_manager.AccountSettings()
                pass
            case 3:
                self.start_trader()

    # ------------------------------------------------------------------
    # Error handling helpers
    # ------------------------------------------------------------------

    def report_error(self, title: str, error: BaseException, with_traceback=False):
        """Logs an error and posts it to the optional Error Webhook."""
        details = f"{type(error).__name__}: {error}"
        if with_traceback:
            details += "\n" + "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        log(f"[BOT] {title}: {details}", severityNum=4 if with_traceback else 3)
        settings = self.rolimons.config.discord_settings
        if settings.get("Hide_Username", True):
            title, details = self.hide_usernames(title), self.hide_usernames(details)
        self.discord_webhook.send_error(
            settings.get("Error_Webhook"), title, f"```{details[-3900:]}```"
        )

    def hide_usernames(self, text: str) -> str:
        """Swaps each account's username for 'account N' (its Account Manager number)."""
        try:
            accounts = self.json.read_data().get("roblox_accounts", [])
        except Exception:  # an error report must never fail
            return text
        names = [(n, str(a.get("username") or "")) for n, a in enumerate(accounts, 1)]
        # Longest first, so a name inside another name can't break it
        for n, name in sorted(names, key=lambda item: -len(item[1])):
            if len(name) >= 3:
                text = re.sub(re.escape(name), f"account {n}", text, flags=re.I)
        return text

    def disable_account(self, account, error: BaseException):
        """Stops using an account for this session, e.g. when its cookie expires."""
        name = getattr(account, "username", "unknown account")
        self.disabled_accounts.add(id(account))
        self.report_error(
            f"{name} disabled: re-add the account in Account Manager", error
        )

    def is_disabled(self, account) -> bool:
        return id(account) in self.disabled_accounts

    def run_safely(self, name, target, *args, restart_delay=30, stop_event=None):
        """
        Thread safety net: runs target, and if it crashes, logs the full error
        and restarts it so one bad response can't silently kill a thread.
        """
        while True:
            try:
                target(*args)
                return
            except Exception as e:
                self.report_error(f"{name} thread crashed, restarting", e, True)
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(restart_delay)

    def start_thread(self, name, target, *args, stop_event=None):
        thread = threading.Thread(
            target=self.run_safely,
            args=(name, target, *args),
            kwargs={"stop_event": stop_event},
            name=name,
            daemon=True,
        )
        thread.start()
        return thread

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def queue_traders(self, roblox_account: RobloxAPI, stop_event: threading.Event):
        """
        This Should be ran in a thread and can be called to stop at any time.
        It uses the roblox account to scrape Roblox Owner API and checks if they arent in the cache
        It also checks if you can trade  with them and adds them into self.user_queue
        """
        while not stop_event.is_set() and not self.is_disabled(roblox_account):
            if len(self.user_queue) > 20:
                time.sleep(40)
                continue

            try:
                random_item = self.rolimons.return_item_to_scan()
            except exceptions_types.NoItemsToScan as e:
                log(f"[OWNERS] {e}", severityNum=3)
                time.sleep(60)
                continue
            except exceptions_types.RolimonsError as e:
                log(f"[ROLIMONS] Waiting for Rolimons data: {e}", severityNum=2)
                time.sleep(30)
                continue

            owners = []
            try:
                active_traders_response = roblox_account.get_active_traders(
                    random_item, owners
                )
            except exceptions_types.CookieInvalid as e:
                self.disable_account(roblox_account, e)
                return
            if active_traders_response is None:
                continue

            if roblox_account.config.debug["show_scanning_users"]:
                log(f"[OWNERS] Found {len(owners)} new owners: {owners}")

            for owner in owners:
                if stop_event.is_set():
                    return
                if int(owner) in roblox_account.all_cached_traders:
                    if roblox_account.config.debug["show_scanning_users"]:
                        log("[OWNERS] Already traded with this player, skipping", dontPrint=True)
                    continue

                roblox_account.all_cached_traders.add(owner)
                try:
                    if not roblox_account.check_can_trade(owner):
                        continue
                    if roblox_account.config.debug["show_scanning_users"]:
                        log(f"[OWNERS] {owner} has trades on, checking their inventory", dontPrint=True)

                    inventory = roblox_account.fetch_inventory(owner)
                except exceptions_types.CookieInvalid as e:
                    self.disable_account(roblox_account, e)
                    return
                except exceptions_types.InventoryUnavailable as e:
                    log(f"Skipping {owner}: {e.cause}", dontPrint=True)
                    continue
                except exceptions_types.TradebotError as e:
                    log(f"[OWNERS] Skipping {owner}: {e}", severityNum=2, dontPrint=True)
                    continue
                finally:
                    time.sleep(0.15)

                if not inventory:
                    log(f"[OWNERS] {owner} has no tradeable items, skipping", dontPrint=True)
                    continue

                if roblox_account.config.debug["show_scanning_users"]:
                    log(f"[OWNERS] Loaded {owner}'s inventory", dontPrint=True)

                # The round may have ended while we were fetching; this inventory
                # was screened for this account, so don't hand it to the next one
                if stop_event.is_set():
                    return
                self.user_queue[owner] = inventory

    def merge_lists(self, list1, list2):
        # Use set to merge and remove duplicates
        return list(set(list1) | set(list2))

    def update_data_thread(self, roblox_accounts=()):
        """
        Updates the table self.rolimons.data whenever rolimons updates.
        If Rolimons is down the old data is kept.
        After each update, re-prices every account's saved outbounds so a
        value drop is caught within ~2 minutes instead of the 30 minute check.
        """
        while True:
            try:
                self.rolimons.update_data()
                self.last_updated_rolimons = time.time()
                self.recheck_outbounds(roblox_accounts)
            except exceptions_types.RolimonsError as e:
                log(f"[ROLIMONS] Update failed, keeping old data: {e}", severityNum=2)
            time.sleep(120)

    def recheck_outbounds(self, roblox_accounts):
        """No Roblox calls unless a trade has to be declined."""
        for account in roblox_accounts:
            if (
                self.is_disabled(account)
                or account.config.debug["dont_check_outbounds"]
            ):
                continue
            try:
                declined = account.recheck_cached_outbounds()
                if declined:
                    log(
                        f"[OUTBOUND] {account.username}: cancelled {declined} after a price change"
                    )
            except exceptions_types.CookieInvalid as e:
                self.disable_account(account, e)
            except exceptions_types.TradebotError as e:
                log(
                    f"[OUTBOUND] Recheck failed for {account.username}: {e}",
                    severityNum=2,
                )

    def check_outbound_thread(self, roblox_accounts):
        def check_oubounds():
            for account in roblox_accounts:
                if self.is_disabled(account):
                    continue
                try:
                    if not account.config.debug["dont_check_outbounds"]:
                        log("[OUTBOUND] Started checking the trades you sent")
                        account.outbound_api_checker()
                    account.check_completeds()
                except exceptions_types.CookieInvalid as e:
                    self.disable_account(account, e)
                except exceptions_types.TradebotError as e:
                    log(
                        f"[OUTBOUND] Check failed for {account.username}, trying again next round: {e}",
                        severityNum=2,
                    )

        check_oubounds()
        self.last_checked_trades = time.time()

        while True:
            if time.time() - self.last_checked_trades >= 1800:
                self.last_checked_trades = time.time()
                check_oubounds()
            time.sleep(5)

    def handle_inbounds_once(self, account):
        """
        One pass over an account's inbound trades: accept those that pass the
        config (if Accept Valid Trades is on), counter the rest (if Counter
        Trades is on). Does nothing in dont_send_trade test mode.
        """
        accept = account.config.inbounds["Accept_Valid_Trades"]
        counter = account.config.inbounds["CounterTrades"]
        if account.config.debug["dont_send_trade"] or not (accept or counter):
            return None
        try:
            results = account.handle_inbounds(accept=accept, counter=counter)
            log(
                f"[INBOUND] {account.username}: accepted {results['accepted']}, "
                f"countered {results['countered']}, "
                f"declined {results.get('declined', 0)}, kept {results['kept']}"
            )
            return results
        except exceptions_types.TradeLimit:
            log(f"[INBOUND] {account.username} hit the daily trade limit while countering")
            if not account.config.debug["ignore_limit"]:
                self.json.add_ratelimit_timestamp(account.cookies[".ROBLOSECURITY"])
        except exceptions_types.CookieInvalid as e:
            self.disable_account(account, e)
        except exceptions_types.TradebotError as e:
            log(f"[INBOUND] Check failed for {account.username}: {e}", severityNum=2)
        return None

    def counter_trade_thread(self, roblox_accounts):
        """Checks every account's inbound trades every Check Inbounds Every Minutes."""
        log("[INBOUND] Started checking trades people send you")
        while True:
            for account in roblox_accounts:
                if self.is_disabled(account):
                    continue
                interval = account.config.inbounds["Check_Every_Minutes"] * 60
                if time.time() - account.counter_timer < interval:
                    continue
                account.counter_timer = time.time()
                self.handle_inbounds_once(account)
            time.sleep(5)

    # ------------------------------------------------------------------
    # Main trading loop
    # ------------------------------------------------------------------

    def start_trade_ads(self, roblox_accounts):
        """Starts posting Rolimons trade ads if [Trade Ads] Enabled = True."""
        config = self.rolimons.config
        if not config.trade_ads["Enabled"]:
            return
        if config.debug["dont_send_trade"]:
            log("[TRADE ADS] Not posting ads: Dont Send Trades is on (test mode)")
            return
        with_cookie = [a for a in roblox_accounts if a.rolimons_cookie]
        if not with_cookie:
            log(
                "[TRADE ADS] No account has a Rolimons cookie. "
                "Add one in Account Manager > Rolimons Cookies.",
                severityNum=2,
            )
            return
        poster = TradeAdPoster(config.trade_ads)
        self.start_thread("Trade ads", self.trade_ad_thread, poster, with_cookie)

    def trade_ad_thread(self, poster, accounts):
        while True:
            poster.run_once([a for a in accounts if not self.is_disabled(a)])
            time.sleep(60)

    def open_account_manager_for_setup(self):
        """No usable accounts: explain why and open the Account Manager."""
        saved = self.json.read_data().get("roblox_accounts", [])
        if not saved:
            reason = "No accounts added yet."
            hint = "Use option 1 (Firefox) or 2 (Manual) to add an account."
        elif not any(a.get("use_account") for a in saved):
            reason = f"All {len(saved)} saved account(s) are turned off."
            hint = "Use option 4 to turn one on, or 1 / 2 to add another account."
        else:
            reason = "None of your enabled accounts could log in (cookie expired?)."
            hint = "Use option 1 (Firefox) or 2 (Manual) to add the account again."
        self.cli.print_error(f"{reason}\nOpening the Account Manager: {hint}")
        input("Press enter to continue.")
        AccountManager().main()

    def start_trader(self):
        """
        Main Loop function that loops through all the accounts
        then run the traders
        """
        roblox_accounts = self.load_roblox_accounts()
        if not roblox_accounts:
            self.open_account_manager_for_setup()
            return

        self.start_thread(
            "Outbound checker", self.check_outbound_thread, roblox_accounts
        )
        self.start_thread("Inbound trades", self.counter_trade_thread, roblox_accounts)
        self.start_thread("Rolimons updater", self.update_data_thread, roblox_accounts)
        self.start_trade_ads(roblox_accounts)

        time.sleep(1)
        while True:
            active_accounts = [a for a in roblox_accounts if not self.is_disabled(a)]
            if not active_accounts:
                input(
                    "Every account is disabled (expired cookies?). Press enter to go back."
                )
                return

            for current_account in active_accounts:
                try:
                    keep_going = self.run_account_round(current_account)
                except exceptions_types.CookieInvalid as e:
                    self.disable_account(current_account, e)
                    keep_going = True
                except exceptions_types.TradebotError as e:
                    log(
                        f"[TRADING] {current_account.username}'s round failed, moving to the next account: {e}",
                        severityNum=2,
                    )
                    keep_going = True
                except Exception as e:
                    self.report_error(
                        f"Unexpected error trading on {current_account.username}",
                        e,
                        True,
                    )
                    keep_going = True
                finally:
                    self.stop_event.set()  # Signal the queue thread to stop

                if not keep_going:
                    break
            time.sleep(5)

    def run_account_round(self, current_account) -> bool:
        """
        One trading round for an account. Returns False when every account is
        trade-limited and the loop should start over after waiting.
        """
        if time.time() - current_account.last_generated_csrf_timer >= 900:
            log("[REQUESTS] Refreshing CSRF token", dontPrint=True)
            current_account.request_handler.generate_csrf()
            current_account.last_generated_csrf_timer = time.time()

        current_account.last_sent_trade = time.time()

        if not current_account.config.debug["ignore_limit"]:
            if self.json.is_all_ratelimited():
                log(
                    "[TRADING] Every account is paused, checking again in 20 minutes:\n"
                    + self.json.paused_text()
                )
                time.sleep(20 * 60)
                return False

            if self.json.check_ratelimit_cookie(
                current_account.cookies[".ROBLOSECURITY"]
            ):
                log(
                    f"[TRADING] {current_account.username} is paused, moving to the next account"
                )
                return True

        try:
            current_account.refresh_self_inventory()
        except exceptions_types.InventoryUnavailable as e:
            log(
                f"[TRADING] Couldn't load {current_account.username}'s inventory, skipping this round: {e.cause}",
                severityNum=2,
            )
            time.sleep(5)
            return True

        if not current_account.account_inventory:
            log(f"[TRADING] {current_account.username} has no items it can trade, pausing it for an hour")
            self.json.add_ratelimit_timestamp(
                current_account.cookies[".ROBLOSECURITY"], "had no items it can trade", hours=1
            )
            time.sleep(5)
            return True

        try:
            is_premium = current_account.check_premium(current_account.account_id)
        except exceptions_types.CookieInvalid:
            raise
        except exceptions_types.TradebotError as e:
            log(
                f"[TRADING] Couldn't check Premium for {current_account.username}, skipping this round: {e}",
                severityNum=2,
            )
            time.sleep(5)
            return True

        if not is_premium:
            log(f"[TRADING] {current_account.username} doesn't have Premium, so it can't trade. Pausing it for an hour")
            self.json.add_ratelimit_timestamp(
                current_account.cookies[".ROBLOSECURITY"], "doesn't have Premium", hours=1
            )
            time.sleep(5)
            return True

        current_account.get_recent_traders()
        log("[TRADING] Loaded recent traders (they get skipped)")
        # TODO: add max days inactive in cfg and parse as arg

        # Fresh stop signal per round so the last account's scanner can't keep running,
        # and drop users that were screened for the previous account
        self.stop_event = threading.Event()
        self.user_queue.clear()
        self.start_thread(
            f"Queue traders ({current_account.username})",
            self.queue_traders,
            current_account,
            self.stop_event,
            stop_event=self.stop_event,
        )

        log("[BOT] Everything is running, trading now")
        self.process_trades_for_account(current_account)
        log("[BOT] Stopping...")
        return True

    def process_trades_for_account(self, account):
        """
        Generates and Starts trading for the given account.
        Returns when the account should hand over to the next one.
        CookieInvalid is raised to the caller.
        """
        TradeDebugSent = 0
        while True:
            # Check if user queue is empty
            while not self.user_queue:
                if self.is_disabled(account):
                    return None
                time.sleep(10)

            log("[TRADING] Started trading", dontPrint=True)
            if not account.account_inventory:
                log("[DEBUG] process account inventory on hold breaking", dontPrint=True)
                return None

            # Using list() creates a copy of the keys
            for trader in list(self.user_queue.keys()):
                max_seconds = account.config.filter_generated[
                    "Max_Seconds_Spent_on_One_User"
                ]
                time_spent = time.time() - account.last_sent_trade
                if time_spent > max_seconds:
                    log(
                        f"[TRADING] No trades found for {account.username} in {max_seconds:g} seconds, moving on"
                    )
                    account.last_sent_trade = time.time()
                    return None
                log(
                    f"[TRADING] {account.username} has searched {time_spent:.0f}s for a trade", dontPrint=True)

                log(f"[TRADING] Checking trader {trader}", dontPrint=True)
                trader_inventory = self.user_queue.pop(trader, None)
                account_inventory = account.account_inventory

                if not account_inventory:
                    log(f"[TRADING] {account.username} has no items it can trade")
                    return None
                if not trader_inventory:
                    continue

                try:
                    result = self.trade_with(
                        account, trader, account_inventory, trader_inventory
                    )
                except exceptions_types.CookieInvalid:
                    raise
                except Exception as e:
                    # Unknown bug: report it, skip this trader, keep trading
                    self.report_error(
                        f"Unexpected error trading with {trader}", e, True
                    )
                    time.sleep(5)
                    continue

                if result == "stop":
                    return False
                if result == "next_account":
                    return None
                if result == "sent":
                    TradeDebugSent += 1
                    log(f"[TRADING] Trades sent this round: {TradeDebugSent}", dontPrint=True)
                if result == "no_trade" and not account.account_inventory:
                    log(
                        "[DEBUG] process account in trading inventory on hold returning", dontPrint=True)
                    return None

    def trade_with(self, account, trader, account_inventory, trader_inventory) -> str:
        """
        Generates and sends one trade. Returns what happened:
        "sent", "no_trade", "skipped", "next_account" or "stop".
        """
        log(f"[TRADING] Generating a trade for {account.username}", dontPrint=True)
        generated_trade = account.trade_maker.generate_trade(
            account_inventory,
            trader_inventory,
            offered=account.offered_item_counts(),
            about=f"{account.username} -> {trader}: ",
        )

        if not generated_trade:
            log(f"[TRADING] No trade generated for {account.username}", dontPrint=True)
            return "no_trade"

        if account.config.debug["trading_debug"]:
            log(f"Generated trade: {generated_trade} {account.username}", severityNum=5)

        self_side = generated_trade["self_side"]
        their_side = generated_trade["their_side"]
        self_robux = generated_trade["self_robux"]

        if not account.config.debug["dont_send_trade"]:
            try:
                account.send_trade(trader, self_side, their_side, self_robux=self_robux)
            except exceptions_types.TradeLimit:
                if account.config.debug["ignore_limit"]:
                    log(f"[TRADING] {account.username} hit its daily trade limit (Ignore trade limit is on, continuing)")
                    return "skipped"
                log(f"[TRADING] {account.username} hit its daily trade limit")
                self.json.add_ratelimit_timestamp(account.cookies[".ROBLOSECURITY"])
                return "stop"
            except exceptions_types.ItemsUnavailable as e:
                log(f"[TRADING] Some items in the trade are gone, reloading inventory: {e}")
                try:
                    account.refresh_self_inventory()
                except exceptions_types.InventoryUnavailable as inv_error:
                    log(f"[TRADING] Couldn't reload inventory: {inv_error.cause}", severityNum=2)
                    return "next_account"
                return "skipped"
            except exceptions_types.UserCannotTrade as e:
                log(f"[TRADING] {trader} can't trade right now: {e}", dontPrint=True)
                return "skipped"
            except exceptions_types.TwoFactorError as e:
                self.report_error(
                    f"2FA failed on {account.username}, moving to next account", e
                )
                return "next_account"
            except exceptions_types.RateLimited as e:
                log(f"[TRADING] Sending trades is rate limited, waiting a minute: {e}", severityNum=2)
                time.sleep(60)
                return "skipped"
            except exceptions_types.CookieInvalid:
                raise
            except exceptions_types.TradebotError as e:
                log(f"[TRADING] Couldn't send a trade to {trader}: {exceptions_types.short_error(e)}", severityNum=2)
                return "skipped"

        account.last_sent_trade = time.time()

        # The trade is sent; a webhook/log problem shouldn't count as a failure
        try:
            self.log_sent_trade(
                account, trader, generated_trade, account_inventory, trader_inventory
            )
        except (exceptions_types.TradebotError, KeyError, TypeError) as e:
            log(
                f"[WEBHOOK] Trade sent to {trader}, but couldn't post the webhook: {e}",
                severityNum=2,
            )
        return "sent"

    def log_sent_trade(
        self, account, trader, generated_trade, account_inventory, trader_inventory
    ):
        def get_duplicate_items(side: tuple, inventory: dict) -> list:
            assetids = []
            for asset_id in side:
                valid_item = inventory.get(asset_id)
                if valid_item:
                    assetids.append(valid_item["item_id"])
            return assetids

        generated_trade["self_side_item_ids"] = get_duplicate_items(
            generated_trade["self_side"], account_inventory
        )
        generated_trade["their_side_item_ids"] = get_duplicate_items(
            generated_trade["their_side"], trader_inventory
        )

        embed_fields, total_profit = self.discord_webhook.embed_fields_from_trade(
            generated_trade,
            self.rolimons.item_data,
            self.rolimons.projected_json.read_cached(),
        )
        embed = self.discord_webhook.setup_embed(
            title=f"Sent a trade with {total_profit} total profit",
            color=1,
            user_id=trader,
            embed_fields=embed_fields,
            footer="Frick shedletsky",
        )
        self.discord_webhook.send_webhook(
            embed, account.config.discord_settings["Send_Webhook"]
        )

        send_items = embed_fields["Send"][0]
        receive_items = embed_fields["Receive"][0]
        if isinstance(send_items, tuple):
            send_items = "\n".join(map(str, send_items))
        if isinstance(receive_items, tuple):
            receive_items = "\n".join(map(str, receive_items))

        breakdown = embed_fields["Trade Breakdown"][0]
        lines = [
            f"[TRADING] {account.username} sent a trade to {trader} "
            f"({total_profit:+,} overall)",
            "You give:",
            *("  " + line for line in send_items.splitlines()),
            "You get:",
            *("  " + line for line in receive_items.splitlines()),
            breakdown,
        ]
        log("\n".join(lines))

    def load_roblox_accounts(self):
        """
        Returns a list of Roblox Classes that were made from the cookie json.
        Accounts that fail to load are reported and skipped.
        """
        log("[BOT] Loading accounts...")
        cookie_json = self.json.read_data()
        roblox_accounts = []

        for account in cookie_json.get("roblox_accounts", []):
            # Dont use account if its disabled
            if not account.get("use_account"):
                continue

            name = account.get("username", "unknown account")
            try:
                roblox_cookie = {".ROBLOSECURITY": account["cookie"]}
                auth_secret = account["auth_secret"]
                user_id = account["user_id"]
            except KeyError as e:
                log(
                    f"[BOT] {name} in cookies.json is missing {e}, skipping it", severityNum=3
                )
                continue

            try:
                roblox_account = RobloxAPI(
                    cookie=roblox_cookie, auth_secret=auth_secret
                )
            except exceptions_types.CookieInvalid as e:
                self.report_error(
                    f"{name}'s cookie is expired or invalid: re-add it in Account Manager",
                    e,
                )
                continue
            except exceptions_types.TradebotError as e:
                self.report_error(f"Couldn't load {name}, skipping it", e)
                continue

            # Optional, for [Trade Ads]
            roblox_account.rolimons_cookie = account.get("rolimons_cookie")

            user_config = self.account_configs.get_config(user_id)
            if user_config:
                roblox_account.config.trading = user_config
            roblox_accounts.append(roblox_account)
        return roblox_accounts


if __name__ == "__main__":
    # Used by the release build to check the program starts
    if "--version" in sys.argv:
        print(full_version())
        sys.exit(0)
    try:
        doggo = Doggo()
        doggo.main()

    except KeyboardInterrupt:
        log("[BOT] Stopped")

    except Exception as e:
        tb = traceback.format_exc()  # Capture the full traceback
        log(f"[BOT] Crashed: {e}\n{tb}", severityNum=4)
        input("Press enter to exit.")

    finally:
        sys.exit()
        quit()
