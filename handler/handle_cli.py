import colorama
import time

from handler.handle_logs import use_color

colorama.init(autoreset=True)

# No color when NO_COLOR is set or the output isn't a terminal; every message
# still says what it is in words ([ERROR], [SUCCESS], ...)
COLOR = use_color()
red = colorama.Fore.RED if COLOR else ""
magenta = colorama.Fore.MAGENTA if COLOR else ""
green = colorama.Fore.GREEN if COLOR else ""
reset = colorama.Style.RESET_ALL if COLOR else ""


class Terminal:
    def __init__(self):
        pass

    @staticmethod
    def print_menu(title, options):
        print(f"---{magenta + title + reset}---")
        for index, option in enumerate(options, 1):
            print(f"[{magenta}{index}{reset}] {option[1]}")

    @staticmethod
    def print_error(message):
        try:
            print("[" + red + "ERROR" + reset + "]", message)
        except UnicodeEncodeError:
            print("ERROR: ", message)
        time.sleep(2)

    @staticmethod
    def print_success(message):
        print("[" + green + "SUCCESS" + reset + "]", message)

    @staticmethod
    def input_prompt(prompt):
        # Color only the word "INPUT", brackets remain uncolored
        return input(f"[{magenta}INPUT{reset}] {prompt} > ")

    @staticmethod
    def clear_console():
        import os

        os.system("cls" if os.name == "nt" else "clear")
