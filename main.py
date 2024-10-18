from handler import *
from roblox_api import RobloxAPI
json_handler = JsonHandler('cookies.json')
roblox_accounts = []
cookie_warning = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_"

if __name__ == "__main__":
    config = ConfigHandler('config.cfg')
    while True:    
        answer = int(input(
            """
    1. Add Cookie
    2. Delete Cookie
    3. Cancel All Trades
    4. Scan inbound Trades
    5. Scan Outbound Trades
    7. Check for expired premium
    8. Start Trade Bot
    Enter Option:
    """))
        if answer == 1:
            acc_cookie = input("Enter Cookie (include warning): ")
            cookie_payload = {'.ROBLOSECURITY': acc_cookie}

            if cookie_warning not in acc_cookie:
                print("Invalid cookie format try again")
                continue

            # CHECK IF COOKIE IN CORRECT
            try:
                roblox_login = RobloxAPI(cookie=cookie_payload)
            except ValueError as e:
                print(e)  # This will print the error message
                print("Not using roblox account...")
                continue

            
            auth_token = input("Enter in 2fa token: ")
            try:
                auth_code = roblox_login.verify_auth()
            except ValueError as e:
                print(e)
                print("Not using account...")
                continue

            json_handler.add_cookie(acc_cookie, auth_token)

            # CHECK IF USER HAS PREMIUM,
            # TAKE USERNAME 
            print("Cookie added successfully.")

        elif answer == 2:
            print("json")
            json_handler.list_cookies()
            index = int(input("Enter the number of the cookie to delete (or -1 to cancel): "))
            if index != -1:
                json_handler.delete_cookie(index)
        elif answer == 3:
            json_handler.list_cookies()
