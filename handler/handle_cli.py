import colorama
import time
colorama.init(autoreset=True)

red = colorama.Fore.RED
magenta = colorama.Fore.MAGENTA
green = colorama.Fore.GREEN
reset = colorama.Style.RESET_ALL
class Terminal:
    def __init__(self):
        pass

    @staticmethod
    def print_menu(title, options):
        print(f"---{magenta+title+reset}---")
        for index, option in enumerate(options, 1):
            print(f"[{colorama.Fore.MAGENTA}{index}{colorama.Style.RESET_ALL}] {option[1]}")

    @staticmethod
    def print_error(message):
        try:
            print('[' + red + "ERROR" + reset + ']', message)
        except:
            print("ERROR: ",message)
        time.sleep(2)


    @staticmethod
    def print_success(message):
        print("[" + green + "SUCCESS" + reset + ']', message)

    @staticmethod
    def input_prompt(prompt):
        # Color only the word "INPUT", brackets remain uncolored
        return input(f"[{magenta}INPUT{reset}] {prompt} > ")

    @staticmethod
    def clear_console():
        import os
        os.system('cls' if os.name == 'nt' else 'clear')


