import handle_requests
import requests
import datetime
import rolimons_api



def main():
    rolimons_api.RolimonAPI().scan_owners()
main()

class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie:dict=None, Proxies=None) -> None:
        self.request_handler = handle_requests.RequestsHandler(cookie=cookie)
        
        # no cookie
        self.parse_handler = handle_requests.RequestsHandler(Proxies) 

    def return_inventory(self, user_id):
        userinventory = self.request_handler.get(f"https://inventory.roblox.com/v1/users/{userid}/assets/collectibles")

        pass

