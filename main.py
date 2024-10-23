import rolimons_api
from handler import *
from roblox_api import RobloxAPI
from trade_algorithm import TradeMaker
from account_manager import AccountManager
import time

class TradeManager:
    def __init__(self):
        pass

class Doggo:
    def __init__(self):
        self.cli = Terminal()
        pass

    def main(self):
        while True:
            self.cli.clear_console()
            options = (
                (1, "Account Manager"),
                (2, "Trade Manager"),
                (3, "Execute Trader"),
            )
            self.cli.print_menu("Main Menu", options)
            try:
                answer = int(self.cli.input_prompt("Enter Option"))
            except ValueError:
                self.cli.print_error("Invalid input. Please enter a number.")
                continue

  #          print(answer)
            match answer:
                case 1:
                    AccountManager().main()
                case 2:
                    pass
 #           time.sleep(2)

if __name__ == "__main__":
    doggo = Doggo()
    doggo.main()

