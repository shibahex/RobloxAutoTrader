import handle_requests
import requests
import json

class Item:
    def __init__(self, item_id, item_name, asset_type_id, original_price, created, 
                 first_timestamp, best_price, favorited, num_sellers, rap, 
                 owners, bc_owners, copies, deleted_copies, bc_copies, 
                 hoarded_copies, acronym, 
                 valuation_method, value, demand, trend, projected, 
                 hyped, rare, thumbnail_url_lg):
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
        self.valuation_method = valuation_method
        self.value = value
        self.demand = demand
        self.trend = trend
        self.projected = projected
        self.hyped = hyped
        self.rare = rare
        self.thumbnail_url_lg = thumbnail_url_lg

    def __repr__(self):
        return (f"item_id={self.item_id}, item_name={self.item_name}, "
                f"best_price={self.best_price}, favorited={self.favorited}, "
                f"thumbnail_url={self.thumbnail_url_lg}")

class RolimonAPI():
    def __init__(self, cookie=None):
        self.Session = requests.Session()
        self.item_data = {}

    def return_formatted_owners(self, item_id: str or int):
        """
            Returns the rolimons.com/item/item_ID bc copies in formated by owners and datetime scanned
        """
        # TODO: Make your own rolimons API
        page_text = handle_requests.RequestsHandler().requestAPI(f"https://www.rolimons.com/item/{item_id}")
        if page_text.status_code != 200:
            print("rolimons items API error:", page_text.status_code)
            return None

        data = page_text.text.split("bc_copies_data")[1].split('[')[1].split("]")[0]

        owners = data.split(',')
        # Make it newest first and remove roblox 
        owners = owners[::-1]
        owners.remove("1")

        return owners

    def scan_owners(self, item_id: str or int):
        """
            returns a list of owners, will return None if errored
        """
        owners = self.return_formatted_owners(item_id)
        if owners:
            return owners
        else:
            print("Failed to retrieve data from Rolimons or no owners found.")
            return None

    def update_data(self):
        """
            scrapes rolimons.com/catalog item_details because the API doesn't show shit like owners 
        """

        page = handle_requests.RequestsHandler().requestAPI("https://www.rolimons.com/catalog")

        item_details = json.loads(page.text.split("var item_details = ")[1].split(";")[0])

        for item in item_details:
            item_info = item_details[item]
            # add in the itemID 
            item_info.insert(0, item)


            self.item_data[item] = Item(*item_details[item])

