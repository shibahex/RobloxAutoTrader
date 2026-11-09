"""
Config Manager: edit config.cfg, per-account settings, and presets.

Main menu -> config.cfg -> a section -> a setting
          -> Account Configs -> an account -> a section -> a setting
          -> Use a Preset for config.cfg

Every setting gets the easiest editor for it: a numbered list for settings
with a few options, True/False, add/remove for item lists (by ID or name),
on/off for tags, and a builder for Pick Trade By. An account config only
holds the settings that differ from config.cfg.
"""

import os
import re
import shutil
import tempfile

from handler.account_settings import (
    ACCOUNT_OPTIONS,
    LIST_OPTIONS,
    HandleConfigs,
    config_text,
    set_options,
    shown_name,
    shown_value,
)
from handler.handle_cli import Terminal, green, magenta, reset
from handler.handle_config import ConfigHandler
from handler.handle_trade_ads import OFFER_PICKS, REQUEST_TAGS

CONFIG_FILE = "config.cfg"
BACKUP_FILE = "config.backup.cfg"


def _file_order() -> dict:
    """(section, option) -> its line in config.default.cfg, to list settings in that order."""
    order, section = {}, None
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.default.cfg")
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].lower()
                elif "=" in line and not line.startswith("#") and section:
                    order[(section, line.split("=")[0].strip().lower())] = n
    except OSError:
        pass
    return order


# Section -> the account settings in it, in config.cfg order
_ORDER = _file_order()
SECTIONS = {}
for _key in sorted(
    ACCOUNT_OPTIONS,
    key=lambda k: _ORDER.get(tuple(p.lower() for p in shown_name(k)), 10**6),
):
    SECTIONS.setdefault(shown_name(_key)[0], []).append(_key)
# Menu order
SECTION_ORDER = ["Profit", "Trade Rules", "Items", "Picking Trades", "Outbounds"]
SECTION_ORDER = [s for s in SECTION_ORDER if s in SECTIONS] + [
    s for s in SECTIONS if s not in SECTION_ORDER
]

DIM = "\033[2m" if magenta else ""

# --- which editor each setting gets (keyed by how config.cfg writes it) -------------

CHOICES = {
    ("profit", "algorithm for valued items"): ["rap_algo", "rolimon_value", "zero_value"],
    ("finding traders", "scan type"): ["rap", "value", "both"],
    ("trade ads", "offer items using"): list(OFFER_PICKS),
}
ITEM_LISTS = {
    ("items", "never give"),
    ("items", "never receive"),
    ("trade ads", "offer item ids"),
    ("trade ads", "request item ids"),
}
TAG_LISTS = {("trade ads", "request tags"): list(REQUEST_TAGS)}
PICK_TRADE_BY = ("picking trades", "pick trade by")

# Pick Trade By options, as the builder lists them
PICK_HELP = {
    "lowest_rap_gain": "smallest RAP gain (fair, accepted more)",
    "highest_rap_gain": "biggest RAP gain",
    "lowest_value_gain": "smallest Value gain",
    "highest_value_gain": "biggest Value gain",
    "lowest_overall_gain": "smallest Overall gain",
    "highest_overall_gain": "biggest Overall gain",
    "lowest_algo_gain": "smallest RAP Algorithm gain",
    "highest_algo_gain": "biggest RAP Algorithm gain",
    "closest_score_based_on_overall_value": "most even trade by Overall",
    "closest_score_based_on_rap": "most even trade by RAP",
    "lowest_sum_of_trade_value": "smallest trade by total Value",
    "highest_sum_of_trade_value": "biggest trade by total Value",
    "lowest_sum_of_trade_rap": "smallest trade by total RAP",
    "highest_sum_of_trade_rap": "biggest trade by total RAP",
    "lowest_sum_of_overall_value": "smallest trade by total Overall",
    "highest_sum_of_overall_value": "biggest trade by total Overall",
    "lowest_demand": "lowest demand of all items",
    "highest_demand": "highest demand of all items",
    "lowest_volume_gain": "least daily sales gained",
    "highest_volume_gain": "most daily sales gained",
    "lowest_sum_of_volume": "least daily sales of all items",
    "highest_sum_of_volume": "most daily sales of all items",
    "upgrade": "you give more items than you get",
    "downgrade": "you get more items than you give",
    "random": "random (in a list: random among ties)",
}

RESET = object()  # an editor's answer: use config.cfg's value (account configs)


def setting_kind(section: str, option: str, current: str):
    """
    How a setting is edited: ("choice", options), ("bool",), ("items",),
    ("tags", options), ("pick",) or ("text",).
    """
    key = (section.lower(), option.lower())
    if key in CHOICES:
        return ("choice", CHOICES[key])
    if key in ITEM_LISTS:
        return ("items",)
    if key in TAG_LISTS:
        return ("tags", TAG_LISTS[key])
    if key == PICK_TRADE_BY:
        return ("pick",)
    if str(current).strip().lower() in ("true", "false"):
        return ("bool",)
    return ("text",)


def split_list(text) -> list:
    """ "1, 2,3" -> ["1", "2", "3"]; None/empty -> []."""
    parts = [p.strip() for p in str(text or "").split(",") if p.strip()]
    return [] if [p.lower() for p in parts] in (["none"], ["null"]) else parts


def join_list(values) -> str:
    return ", ".join(map(str, values)) if values else "None"


def pick_parts(text) -> tuple[str, list]:
    """Pick Trade By -> (mode, [options]); mode is single, tiebreak or blend."""
    from trade_algorithm import is_blend

    text = str(text or "").strip()
    if is_blend(text):
        body = text.split(":", 1)[1].replace("+", ",")
        return "blend", [p.strip().lower() for p in body.split(",") if p.strip()]
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    return ("tiebreak" if len(parts) > 1 else "single"), parts


def pick_text(mode, names) -> str:
    if mode == "blend":
        return "blend: " + ", ".join(names)
    return " + ".join(names)


# --- config.cfg as text --------------------------------------------------------------


def read_settings(text: str) -> list:
    """
    config.cfg's sections in file order: [(section, [(option, value, help)])].
    help is the comment block right above the setting (or the one before it,
    for settings grouped under one note).
    """
    sections, current, comments = [], None, []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = (stripped[1:-1], [])
            sections.append(current)
            comments = []
        elif stripped.startswith("#"):
            note = stripped[1:]
            comments.append((note[1:] if note.startswith(" ") else note).rstrip())
        elif not stripped:
            comments = []
        elif current is not None and ("=" in stripped or ":" in stripped):
            option, _, value = re.split(r"(\s*[=:]\s*)", stripped, maxsplit=1)
            help_text = "\n".join(comments)
            if not help_text and current[1]:
                help_text = current[1][-1][2]
            current[1].append((option.strip(), value.strip(), help_text))
            comments = []
    return [s for s in sections if s[1]]


def check_config_text(text: str) -> str | None:
    """None when the config loads, else why it doesn't."""
    fd, path = tempfile.mkstemp(suffix=".cfg")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        ConfigHandler(path)
        return None
    except Exception as e:  # noqa: BLE001 - any load error means don't save
        return str(e)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# --- item names (for Never Give / Never Receive...) ---------------------------------


class ItemNames:
    """Rolimons item names, loaded once when an item list is edited."""

    URL = "https://api.rolimons.com/items/v2/itemdetails"

    def __init__(self, fetch=None):
        self.fetch = fetch
        self.items = None  # id -> (name, acronym)

    def load(self):
        if self.items is not None:
            return self.items
        try:
            if self.fetch:
                data = self.fetch()
            else:
                import requests

                data = requests.get(self.URL, timeout=15).json()
            self.items = {
                str(item_id): (str(info[0]).strip(), str(info[1] or "").strip())
                for item_id, info in data.get("items", {}).items()
            }
        except Exception:  # noqa: BLE001 - names are a nice-to-have
            self.items = {}
        return self.items

    def name(self, item_id) -> str:
        info = self.load().get(str(item_id).split(":")[-1])
        return info[0] if info else ""

    def search(self, text: str) -> list:
        """Item IDs matching a name or acronym: exact matches, else names containing it."""
        wanted = text.strip().lower()
        items = self.load()
        exact = [i for i, (name, acronym) in items.items()
                 if wanted in (name.lower(), acronym.lower())]
        if exact:
            return exact
        return [i for i, (name, _) in items.items() if wanted in name.lower()]


class AccountSettings:
    def __init__(self, ask=None, run=True, config_file=CONFIG_FILE, item_names=None):
        self.configs = HandleConfigs()
        self.cli = Terminal()
        self.ask = ask or self.cli.input_prompt
        self.config_file = config_file
        self.item_names = item_names or ItemNames()
        self.backed_up = False
        if run:
            self.main()

    # --- helpers -----------------------------------------------------------------

    def menu(self, title, groups, back="Back", intro=None) -> int | None:
        """
        Clears the screen and shows a numbered menu, Back last.
        groups: [(heading or None, [option text, ...]), ...]. Numbers run on
        across groups. Returns the 0-based choice, or None for Back.
        """
        options = [text for _, rows in groups for text in rows]
        width = len(str(len(options) + 1))
        while True:
            self.cli.clear_console()
            print(f"---{magenta}{title}{reset}---")
            if intro:
                print(intro)
            n = 0
            for heading, rows in groups:
                if heading:
                    print(f"\n{DIM}{heading}{reset}")
                for text in rows:
                    n += 1
                    print(f"[{magenta}{n:>{width}}{reset}] {text}")
            print()
            print(f"[{magenta}{len(options) + 1:>{width}}{reset}] {back}  {DIM}(or press enter){reset}")
            answer = self.ask("Enter Option").strip()
            if not answer:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(options) + 1:
                return None if int(answer) == len(options) + 1 else int(answer) - 1
            self.cli.print_error(f"Enter a number from 1 to {len(options) + 1}.")

    def accounts(self) -> list[dict]:
        return self.configs.cookies.read_data().get("roblox_accounts", [])

    def pause(self):
        self.ask("Press enter to continue")

    # --- menus -----------------------------------------------------------------------

    def main(self):
        while True:
            choice = self.menu(
                "Config Manager",
                [(None, [
                    f"Edit {self.config_file}  {DIM}(every account uses it){reset}",
                    f"Account Configs  {DIM}(settings for one account only){reset}",
                    f"Use a Preset for {self.config_file}",
                ])],
                back="Back to Main Menu",
            )
            if choice is None:
                return
            if choice == 0:
                self.main_config()
            elif choice == 1:
                self.account_list()
            else:
                self.cli.clear_console()
                self.configs.show_presets()

    # --- config.cfg ---------------------------------------------------------------------

    def read_main(self) -> str:
        with open(self.config_file, encoding="utf-8") as f:
            return f.read()

    def main_config(self):
        while True:
            try:
                sections = read_settings(self.read_main())
            except OSError as e:
                self.cli.print_error(f"Couldn't read {self.config_file}: {e}")
                return
            names = [name for name, _ in sections]
            choice = self.menu(self.config_file, [(None, names)])
            if choice is None:
                return
            self.main_section(names[choice])

    def main_section(self, section):
        while True:
            settings = dict(read_settings(self.read_main())).get(section, [])
            if not settings:
                return
            width = max(len(option) for option, _, _ in settings)
            rows = [f"{option:<{width}}   {value}" for option, value, _ in settings]
            choice = self.menu(f"{self.config_file} > {section}", [(None, rows)])
            if choice is None:
                return
            option, value, help_text = settings[choice]
            new = self.edit_value(
                f"{section} > {option}", setting_kind(section, option, value), value, help_text
            )
            if new is None or new is RESET or new == value:
                continue
            self.save_main(section, option, new)

    def save_main(self, section, option, new) -> bool:
        """Writes one setting into config.cfg if it still loads (backed up once first)."""
        text = self.read_main()
        new_text, changes = set_options(text, {(section, option): new})
        if not changes:
            return False
        problem = check_config_text(new_text)
        if problem:
            self.cli.print_error(f"Not saved, the config wouldn't load: {problem}")
            self.pause()
            return False
        if not self.backed_up:
            shutil.copyfile(self.config_file, BACKUP_FILE)
            self.backed_up = True
        with open(self.config_file, "w", encoding="utf-8") as f:
            f.write(new_text)
        # Accounts compare against config.cfg's values
        self.configs = HandleConfigs()
        return True

    # --- account configs ----------------------------------------------------------------

    def account_list(self):
        while True:
            accounts = self.accounts()
            if not accounts:
                self.cli.print_error("No accounts yet. Add one in Account Manager.")
                return
            names = [str(a.get("username", a["user_id"])) for a in accounts]
            width = max(map(len, names))
            rows = []
            for name, account in zip(names, accounts):
                own = len(self.configs.get_config(account["user_id"]))
                note = (
                    f"{green}{own} own setting{'s' if own != 1 else ''}{reset}"
                    if own
                    else f"{DIM}uses config.cfg{reset}"
                )
                rows.append(f"{name:<{width}}   {note}")
            choice = self.menu("Account Configs", [(None, rows)])
            if choice is None:
                return
            self.account_menu(accounts[choice])

    def account_menu(self, account):
        user_id = str(account["user_id"])
        name = account.get("username", user_id)
        width = max(map(len, SECTION_ORDER))
        while True:
            own = self.configs.get_config(user_id)
            sections = []
            for section in SECTION_ORDER:
                changed = sum(1 for k in SECTIONS.get(section, []) if k in own)
                note = f"{green}{changed} changed{reset}" if changed else ""
                sections.append(f"{section:<{width}}   {note}".rstrip())
            actions = [
                "Copy These Settings Into config.cfg",
                "Reset to config.cfg (remove all of this account's settings)",
            ]
            choice = self.menu(name, [("Settings", sections), ("Actions", actions)])
            if choice is None:
                return
            if choice < len(sections):
                self.section_menu(user_id, name, SECTION_ORDER[choice])
                continue
            self.cli.clear_console()
            if choice == len(sections):
                if not own:
                    print(f"{name} has no settings of its own.")
                else:
                    self.configs.apply_to_main(user_id, ask=self.ask)
                    self.configs = HandleConfigs()
            elif self.ask(f"Remove all of {name}'s own settings? (y/n)").strip().lower() == "y":
                self.configs.delete_config(user_id)
                print(f"{name} uses config.cfg now.")
            self.pause()

    def section_menu(self, user_id, name, section):
        keys = SECTIONS.get(section, [])
        labels = [shown_name(k)[1] for k in keys]
        width = max(map(len, labels))
        while True:
            own = self.configs.get_config(user_id)
            values = [
                shown_value(k, own[k] if k in own else self.configs.main_values.get(k))
                for k in keys
            ]
            value_width = max(map(len, values))
            rows = []
            for key, label, value in zip(keys, labels, values):
                if key in own:
                    main = shown_value(key, self.configs.main_values.get(key))
                    rows.append(
                        f"{label:<{width}}   {green}{value:<{value_width}}{reset}"
                        f"   {DIM}config.cfg: {main}{reset}"
                    )
                else:
                    rows.append(f"{label:<{width}}   {value}")
            choice = self.menu(
                f"{name} > {section}",
                [(f"{green}Green{reset}{DIM} = this account's own value. "
                  f"The rest come from config.cfg.", rows)],
            )
            if choice is None:
                return
            self.edit(user_id, keys[choice])

    def account_text(self, key, value) -> str:
        """An account value as config.cfg would write it, for the editors."""
        if key in LIST_OPTIONS:
            return join_list(value or [])
        if value in (None, "Not Set") and isinstance(self.configs.main_values.get(key), bool):
            return "False"
        return config_text(key, value)

    def edit(self, user_id, key):
        section, option = shown_name(key)
        own = self.configs.get_config(user_id)
        main_value = self.configs.main_values.get(key)
        current = self.account_text(key, own[key] if key in own else main_value)
        kind = setting_kind(section, option, self.account_text(key, main_value))
        if kind == ("text",) and isinstance(main_value, bool):
            kind = ("bool",)
        note = (
            f"This account: {shown_value(key, own[key]) if key in own else '(not set)'}\n"
            f"config.cfg:   {shown_value(key, main_value)}"
        )
        while True:
            new = self.edit_value(
                f"{section} > {option}", kind, current, self.help_for(section, option),
                note=note, can_reset=True,
            )
            if new is None:
                return
            if new is RESET:
                self.configs.reset_value(user_id, key)
                return
            try:
                value = self.configs.parse(key, new)
            except ValueError as e:
                self.cli.print_error(f"Not saved: {e}")
                current = new if kind[0] == "pick" else current
                continue
            self.configs.set_value(user_id, key, value)
            return

    def help_for(self, section, option) -> str:
        try:
            settings = dict(read_settings(self.read_main())).get(section, [])
        except OSError:
            return ""
        for name, _, help_text in settings:
            if name.lower() == option.lower():
                return help_text
        return ""

    # --- editors: each returns the new value as config.cfg text, None to go back,
    # or RESET (account configs: use config.cfg's value) ------------------------------

    def edit_value(self, title, kind, current, help_text="", note=None, can_reset=False):
        intro = "\n".join(
            part for part in (
                f"{DIM}{help_text}{reset}" if help_text else "",
                note or f"Now: {current}",
            ) if part
        )
        editors = {
            "choice": lambda: self.edit_choice(title, kind[1], current, intro, can_reset),
            "bool": lambda: self.edit_choice(title, ["True", "False"], current, intro, can_reset),
            "items": lambda: self.edit_items(title, current, intro, can_reset),
            "tags": lambda: self.edit_tags(title, kind[1], current, intro, can_reset),
            "pick": lambda: self.edit_pick(title, current, intro, can_reset),
        }
        return editors.get(kind[0], lambda: self.edit_text(title, current, intro, can_reset))()

    def edit_choice(self, title, options, current, intro, can_reset):
        rows = [
            f"{option}  {green}(now){reset}" if option.lower() == str(current).lower() else option
            for option in options
        ]
        actions = ["Use config.cfg's value"] if can_reset else []
        choice = self.menu(title, [(None, rows), (None, actions)], intro=intro)
        if choice is None:
            return None
        return options[choice] if choice < len(options) else RESET

    def edit_text(self, title, current, intro, can_reset):
        self.cli.clear_console()
        print(f"---{magenta}{title}{reset}---")
        print(intro)
        print("\nType the new value (None turns most limits off).")
        if can_reset:
            print("Type reset to use config.cfg's value.")
        print("Press enter to go back without changing it.")
        text = self.ask("New value").strip()
        if not text:
            return None
        if can_reset and text.lower() == "reset":
            return RESET
        return text

    def edit_items(self, title, current, intro, can_reset):
        """Add items by ID or name, remove them by number."""
        items = split_list(current)
        while True:
            self.cli.clear_console()
            print(f"---{magenta}{title}{reset}---")
            print(intro)
            print()
            if items:
                for n, item_id in enumerate(items, 1):
                    name = self.item_names.name(item_id)
                    print(f"[{magenta}{n}{reset}] {item_id}  {name}")
            else:
                print(f"{DIM}(empty){reset}")
            print(
                f"\nType item IDs or names to {green}add{reset} (several: separate with commas)."
                f"\nType a number from the list to {green}remove{reset} it, clear to empty it,"
                + (" reset to use config.cfg's," if can_reset else "")
                + f"\n{green}save{reset} to keep the list, or press enter to go back without saving."
            )
            answer = self.ask("Item").strip()
            lowered = answer.lower()
            if not answer:
                return None
            if lowered == "save":
                return join_list(items)
            if lowered == "clear":
                items = []
                continue
            if can_reset and lowered == "reset":
                return RESET
            if answer.isdigit() and 1 <= int(answer) <= len(items) and len(answer) < 5:
                items.pop(int(answer) - 1)
                continue
            for part in split_list(answer):
                found = self.find_item(part)
                if found and found not in items:
                    items.append(found)

    def find_item(self, text) -> str | None:
        """An item ID from an ID or a name (asks which one when several match)."""
        text = text.strip()
        if text.split(":")[-1].isdigit():
            return text.split(":")[-1]
        matches = self.item_names.search(text)
        if not matches:
            self.cli.print_error(f"No item called {text!r} (or the item list couldn't load).")
            return None
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 20:
            self.cli.print_error(f"{len(matches)} items match {text!r}, type more of the name.")
            return None
        rows = [f"{self.item_names.name(i)}  {DIM}{i}{reset}" for i in matches]
        choice = self.menu(f"Which {text!r}?", [(None, rows)])
        return None if choice is None else matches[choice]

    def edit_tags(self, title, options, current, intro, can_reset):
        """Turn each tag on or off."""
        chosen = [t.lower() for t in split_list(current)]
        while True:
            rows = [
                f"{green}[x]{reset} {option}" if option in chosen else f"[ ] {option}"
                for option in options
            ]
            actions = [f"{green}Save{reset}: {join_list(chosen)}"]
            if can_reset:
                actions.append("Use config.cfg's value")
            choice = self.menu(
                title, [("Pick a tag to turn it on or off", rows), (None, actions)],
                back="Back without saving", intro=intro,
            )
            if choice is None:
                return None
            if choice < len(options):
                option = options[choice]
                if option in chosen:
                    chosen.remove(option)
                else:
                    chosen.append(option)
                continue
            return join_list(chosen) if choice == len(options) else RESET

    def edit_pick(self, title, current, intro, can_reset):
        """Pick Trade By builder: one option, tie-breakers, or a blend."""
        from trade_algorithm import SELECT_TRADE_OPTIONS

        mode, names = pick_parts(current)
        modes = {
            "single": "One option",
            "tiebreak": "Tie-breakers (+): the first decides, the next breaks its ties",
            "blend": "Blend: every option counts, the first counts most",
        }
        while True:
            if mode == "blend" and names:
                weights = range(len(names), 0, -1)
                listed = [f"{n}  {DIM}(weight {w}){reset}" for n, w in zip(names, weights)]
            else:
                listed = names
            rows = [f"Mode: {modes[mode]}"]
            rows += [f"Add an option{' (replaces it)' if mode == 'single' else ''}"]
            rows += [f"{n}  {DIM}(move or remove){reset}" for n in listed]
            actions = [f"{green}Save{reset}: {pick_text(mode, names) or '(nothing yet)'}"]
            if can_reset:
                actions.append("Use config.cfg's value")
            choice = self.menu(
                title, [(None, rows), (None, actions)], back="Back without saving", intro=intro
            )
            if choice is None:
                return None
            if choice == 0:
                picked = self.menu("Mode", [(None, list(modes.values()))])
                if picked is not None:
                    mode = list(modes)[picked]
                    if mode == "single":
                        names = names[:1]
                continue
            if choice == 1:
                # Grouped like PICK_HELP lists them
                ordered = [o for o in PICK_HELP if o in SELECT_TRADE_OPTIONS]
                ordered += [o for o in SELECT_TRADE_OPTIONS if o not in ordered]
                available = [o for o in ordered if o not in names]
                width = max(map(len, available))
                picked = self.menu(
                    "Add an option",
                    [(None, [f"{o:<{width}}  {DIM}{PICK_HELP.get(o, '')}{reset}" for o in available])],
                )
                if picked is not None:
                    names = [available[picked]] if mode == "single" else names + [available[picked]]
                continue
            if choice < 2 + len(names):
                at = choice - 2
                action = self.menu(names[at], [(None, ["Move up", "Move down", "Remove"])])
                if action == 0 and at > 0:
                    names[at - 1], names[at] = names[at], names[at - 1]
                elif action == 1 and at < len(names) - 1:
                    names[at + 1], names[at] = names[at], names[at + 1]
                elif action == 2:
                    names.pop(at)
                continue
            if choice == 2 + len(names):
                if not names:
                    self.cli.print_error("Add at least one option first.")
                    continue
                return pick_text(mode, names)
            return RESET
