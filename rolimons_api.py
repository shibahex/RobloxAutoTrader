import requests
import json
from handler import *
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
    def __init__(self, cookie:dict=None):
        self.item_data = {}
        self.rolimon_account = RequestsHandler(use_proxies=False, cookie=cookie)
        self.rolimon_parser = RequestsHandler()
        self.config = ConfigHandler('config.ini')
        print(self.config.scan_items)
        print(self.config.filter_users)
        
    def return_item_to_scan(self):
        minimum_value = self.config.scan_items['Minimum_Value_of_Item']
        minimum_rap = self.config.scan_items['Minimum_Rap_of_Item']
        minimum_owners = self.config.scan_items['Minimum_Owners_of_Item']
        minimum_demand = self.config.scan_items['Minimum_Demand_of_Item']
        minimum_trend = self.config.scan_items['Minimum_Trend_of_Item']
        scan_rares = self.config.scan_items['Scan_Rares']

        if self.item_data == {}:
            self.update_data()
        for i in self.item_data.values():
            print(i['value'])
        filtered_items = [
            item for item in self.item_data.values() 
            if (
                (item['original_price'] is None or item['original_price'] >= minimum_value) and
                (item['rap'] is None or item['rap'] >= minimum_rap) and
                (item['owners'] is None or item['owners'] >= minimum_owners) and
                (item['demand'] is None or item['demand'] >= minimum_demand) and
                (item['trend'] is None or item['trend'] >= minimum_trend) and
                (scan_rares or item.get('rare') is not None) 
            )
        ]
        
        print(filtered_items)

    def return_formatted_owners(self, item_id: str or int):
        """
            Returns the rolimons.com/item/item_ID bc copies in formated by owners and datetime scanned
        """
        # TODO: Make your own rolimons API
        page_text = self.rolimon_parser.requestAPI(f"https://www.rolimons.com/item/{item_id}")
        if page_text.status_code != 200:
            print("rolimons items API error:", page_text.status_code)
            return None

        data = page_text.text.split("bc_copies_data")[1].split('[')[1].split("]")[0]

        owners = data.split(',')
        # Make it newest first and remove roblox 
        owners = owners[::-1]
        owners.remove("1")

        return owners


    def update_data(self):
        """
            scrapes rolimons.com/catalog item_details because the API doesn't show shit like owners 
        """

        page = self.rolimon_parser.requestAPI("https://www.rolimons.com/catalog")

        item_details = json.loads(page.text.split("var item_details = ")[1].split(";")[0])

        for item in item_details:
            item_info = item_details[item]
            # add in the itemID 
            item_info.insert(0, item)
            self.item_data[item] = Item(*item_details[item]).to_dict()
    
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


RolimonAPI().return_item_to_scan()
