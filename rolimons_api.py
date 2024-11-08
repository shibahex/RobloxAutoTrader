import requests
import json
import random
from handler import *
import roblox_api
class Item:
    def __init__(self, item_id, item_name, asset_type_id, original_price, created, 
                 first_timestamp, best_price, favorited, num_sellers, rap, 
                 owners, bc_owners, copies, deleted_copies, bc_copies, 
                 hoarded_copies, acronym, 
                 value, demand, trend, projected, 
                 hyped, rare, total_value, thumbnail_url_lg):
        self.item_id = item_id
        self.item_name = item_name
        self.asset_type_id = asset_type_id
        self.original_price = original_price
        self.created = created
        self.first_timestamp = first_timestamp
        self.best_price = best_price
        self.favorited = favorited
        self.num_sellers = num_sellers
        self.rap = rap
        self.owners = owners
        self.bc_owners = bc_owners
        self.copies = copies
        self.deleted_copies = deleted_copies
        self.bc_copies = bc_copies
        self.hoarded_copies = hoarded_copies
        self.acronym = acronym
        #self.valuation_method = valuation_method
        self.value = value
        self.demand = demand
        self.trend = trend
        self.projected = projected
        self.hyped = hyped
        self.rare = rare
        self.total_value = total_value
        self.thumbnail_url_lg = thumbnail_url_lg

    def __repr__(self):
        return self.to_dict()

    def to_dict(self):
        return {
            'item_id': self.item_id,
            'item_name': self.item_name,
            'asset_type_id': self.asset_type_id,
            'original_price': self.original_price,
            'created': self.created,
            'first_timestamp': self.first_timestamp,
            'best_price': self.best_price,
            'favorited': self.favorited,
            'num_sellers': self.num_sellers,
            'rap': self.rap,
            'owners': self.owners,
            'bc_owners': self.bc_owners,
            'copies': self.copies,
            'deleted_copies': self.deleted_copies,
            'bc_copies': self.bc_copies,
            'hoarded_copies': self.hoarded_copies,
            'acronym': self.acronym,
            #'valuation_method': self.valuation_method,
            'value': self.value,
            'demand': self.demand,
            'trend': self.trend,
            'projected': self.projected,
            'hyped': self.hyped,
            'rare': self.rare,
            'total_value': self.total_value,
            'thumbnail_url_lg': self.thumbnail_url_lg
        }
class RolimonAPI():
    # make it so its only one instance
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(RolimonAPI, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, cookie:dict=None):
        if self.__initialized:
            return
        self.__initialized = True  # Avoid reinitialization
        self.item_data = {}
        self.rolimon_account = RequestsHandler(use_proxies=False, cookie=cookie)
        self.rolimon_parser = RequestsHandler()
        self.projected_json = JsonHandler('projected_checker.json')

        self.config = ConfigHandler('config.cfg')
        
        self.update_data()
        # ItemID: Timestamp
        self.scanned_items_for_owners = {}
        #print(self.config.filter_users)
        
    def return_item_to_scan(self) -> str:
        minimum_value = self.config.scan_items['Minimum_Value_of_Item']
        minimum_rap = self.config.scan_items['Minimum_Rap_of_Item']
        minimum_owners = self.config.scan_items['Minimum_Owners_of_Item']
        minimum_demand = self.config.scan_items['Minimum_Demand_of_Item']
        minimum_trend = self.config.scan_items['Minimum_Trend_of_Item']
        scan_type = self.config.scan_items['Scan_Type']
        scan_rares = self.config.scan_items['Scan_Rares']

        if self.item_data == {}:
            self.update_data()
        #for item in self.item_data.values():
         #   print(item['item_name'], item['trend'])
        filtered_items = [
            item for item in self.item_data.values() 
            if (
                (scan_type.lower() == "rap" and not item['value']) or
                (scan_type.lower() == "value" and item['value']) or 
                (scan_type.lower() == "both" and
                 (
                 (scan_rares and item['rare']) or
                 (not scan_rares and not item['rare'])
                 )
                 )
            ) and (
                (item['value'] is None or item['value'] >= minimum_value) and
                (item['rap'] is None or item['rap'] >= minimum_rap) and
                (item['owners'] is None or item['owners'] >= minimum_owners) and
                (item['demand'] is None or item['demand'] >= minimum_demand) and
                (item['trend'] is None or item['trend'] >= minimum_trend)
            )
        ]
        print("[DOGGO] Picking random item from list size:", len(filtered_items))
        
        #TODO: add into table with timestamp and if we get the same item check if the time has been 30 minutes and if it has remove and return it 
        return random.choice(filtered_items)
        #print(filtered_items)

    def return_formatted_owners(self, item_id: str or int) -> list:
        """
            Returns the rolimons.com/item/item_ID bc copies in formated by owners and datetime scanned
        """
        # Define the headers to mimic a real browser request
        header = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',  # Can be adjusted based on your preferred language
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',  # Mimicking a referer header
            'Cache-Control': 'max-age=0'
        }

        # Optionally, set cookies if the site requires them (can capture cookies using browser dev tools)
        cookies = {
            'some_cookie_name': 'cookie_value',  # Add your captured cookies here
        }
        # TODO: Make your own rolimons API
        page_text = requests.get(f"https://www.rolimons.com/item/{item_id}", headers=header)
        if page_text.status_code != 200:
            print("rolimons items API error:", page_text.status_code)
            return None

        data = page_text.text.split("bc_copies_data")[1].split('[')[1].split("]")[0]

        owners = data.split(',')
        # Make it newest first and remove roblox 
        owners = owners[::-1]
        owners.remove("1")


        return owners

    #TODO: use selenium to get inventory (forced to because Owner since is tracked in the rolimon backend and isnt an API)
    def get_inventory(self, user_id, applyNFT=False) -> dict:
        get_profile_inventory = Chrome().get_profile_data(user_id, applyNFT)

        print("Got inventory from selenium")
        filtered_inventory = {}

        if get_profile_inventory:
            for item in get_profile_inventory:
                asset_id = get_profile_inventory[item]['item_id']
                # total value reutns the RAP if theres no value
                
                value = self.item_data[asset_id]['total_value']
                rap = self.item_data[asset_id]['rap']
                if rap == value:
                    # Check if the asset_id is in the projected JSON file
                    projected_data = self.projected_json.read_data()
                    existing_item = False
                    for projected_item in projected_data:
                        if int(asset_id) == int(projected_item):
                            existing_item = True

                    
                    if existing_item:
                        is_projected = projected_data[asset_id]['is_projected']
                        if is_projected:
                            continue
                        else:
                            print(f"Asset ID {asset_id} is marked as not projected. Skipping.")
                    else:
                        # If asset_id does not exist in the JSON, check projection status
                        is_projected = roblox_api.RobloxAPI().is_projected(asset_id)
                        if is_projected:
                            self.projected_json.update_projected_status(asset_id, is_projected)
                            continue
                        else:
                            print(f"Asset ID {asset_id} is not projected.")
                            self.projected_json.update_projected_status(asset_id, is_projected)



                filtered_inventory[item] = {
                    'item_id': asset_id,
                    'value': value,
                    'rap': rap,
                    'owner_since': get_profile_inventory[item]['owner_since']
                }

            # apply more usefull info about the item
            return filtered_inventory
        else:
            return False


    
    def update_data(self) -> None:
        """
            scrapes rolimons.com/catalog item_details because the API doesn't show shit like owners 
        """

        page = self.rolimon_parser.requestAPI("https://www.rolimons.com/catalog")
        if page.status_code == 200:
            item_details = json.loads(page.text.split("var item_details = ")[1].split(";")[0])
            for item in item_details:
                item_info = item_details[item]
                # add in the itemID 
                item_info.insert(0, item)
                self.item_data[item] = Item(*item_details[item]).to_dict()
        else:
            print("Couldnt get rolimon data")
            return False
    
    def return_trade_ads(self):
        
        get_ads_response =  self.rolimon_parser.requestAPI("https://api.rolimons.com/tradeads/v1/getrecentads")
        response = get_ads_response.json()
        if response['success'] == False:
            return False

        return response['trade_ads']
            # 6 downgrade
            # 1 demand
            # 5 upgrade 
            # 10 adds 
    def post_trade_ad(self):
        pass
    # Check config to see if we need to filter this user
    def activity_algorithm(self, userid):
        pass

    def validate_user(self, userid):
        # If can trade
        # Last Online 
        # Last Traded
        # Min total value and items
        # Rolimon verified badge
        # Have an algorithm to check how much a person trades (take into fact their graph and how many of their items is owned since)
        pass


