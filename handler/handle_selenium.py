import os
import re
import time
from handler import *
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

class Chrome:
    """
    Handles all Selenium settings and has methods to fetch data.
    """
    def __init__(self, debugMode=False, proxies=None):
        #TODO: read proxies.txt but add after I make the proxy formatter
        self.proxies = proxies or []  # List of proxies to use
        self.current_proxy_index = 0  # Index to track current proxy
        self.proxy_cooldown = {}  # Dictionary to track cooldown status of proxies

        self.config = ConfigHandler('config.cfg')
        # Get browser depending on OS 
        chrome_driver_path = None
        if os.name == 'posix':
            chrome_driver_path = 'chromedriver-linux64/chromedriver'
            chrome_binary_path = 'chrome-linux64/chrome'
        elif os.name == 'nt':
            chrome_driver_path = 'chromedriver-win64/chromedriver.exe'
            chrome_binary_path = 'chrome-win64/chrome.exe'
        else:
            raise OSError("Unsupported OS")

        self.chrome_options = Options()
        if not debugMode:
            self.chrome_options.add_argument('--headless')  # NO GUI
        
        # Helps avoid some issues in certain environments
        self.chrome_options.add_argument('--no-sandbox')  
        self.chrome_options.add_argument('--disable-dev-shm-usage') 
        self.chrome_options.binary_location = chrome_binary_path
        
        self.initialize_browser(chrome_driver_path)

    """
        Base Selenium Functions to setup the browser, load the page and use proxies
    """
    def initialize_browser(self, chrome_driver_path):
        """Initializes the Chrome browser with the current proxy."""
        proxy = self.get_current_proxy()
        if proxy:
            self.chrome_options.add_argument(f'--proxy-server={proxy}')

        service = Service(chrome_driver_path)
        self.browser = webdriver.Chrome(service=service, options=self.chrome_options)

    def get_current_proxy(self):
        """Returns the current proxy, if not in cooldown."""
        proxy = self.proxies[self.current_proxy_index] if self.proxies else None
        if proxy and self.is_proxy_cooldown(proxy):
            return None
        return proxy

    def is_proxy_cooldown(self, proxy):
        """Checks if a proxy is in cooldown."""
        return proxy in self.proxy_cooldown and time.time() < self.proxy_cooldown[proxy]

    def change_proxy(self):
        """Changes to the next proxy in the list."""
        if self.proxies:
            current_proxy = self.get_current_proxy()
            if current_proxy:
                # Put the current proxy on cooldown
                self.proxy_cooldown[current_proxy] = time.time() + 600  # 10 minutes cooldown

            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
            print(f"Switched to proxy: {self.get_current_proxy()}")
            self.initialize_browser()  # Reinitialize the browser with the new proxy

    def parse_time_ago_to_epoch(self, time_str):
        now = datetime.now()
        # Clean the input string by removing extra spaces
        time_str = time_str.replace('\n', ' ').strip()

        if "Awaiting" in time_str:
            return int(now.timestamp())

        try:
            # Adjusted regex pattern to match leading text followed by time description (including hours)
            pattern = r'.*(\d+)\s*(day|days|month|months|year|years|hour|hours)\s*ago'
            match = re.search(pattern, time_str)
        except Exception as e:
            print(time_str, "error:", e)
            raise

        if not match:
            raise ValueError("Invalid time format", time_str)

        value = int(match.group(1))
        unit = match.group(2)

        if unit.startswith('day'):
            target_time = now - timedelta(days=value)
        elif unit.startswith('month'):
            target_time = now - timedelta(days=value * 30)  # Approximation
        elif unit.startswith('year'):
            target_time = now - timedelta(days=value * 365)  # Approximation
        elif unit.startswith('hour'):
            target_time = now - timedelta(hours=value)
        else:
            raise ValueError("Unsupported time unit")

        return int(target_time.timestamp())


    def scroll_to_bottom(self):
        last_height = self.browser.execute_script("return document.body.scrollHeight")
        while True:
            self.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load page
            time.sleep(.5)

            # Calculate new scroll height and compare with last scroll height
            new_height = self.browser.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    """
        Functions to scrape the rolimons player website
    """
    def filter_inventory():
       pass 

    def load_rolimons_page(self, target_url):
        if self.browser.current_url != target_url:
            max_attemps = 10
            for attemp in range(max_attemps):
                self.browser.get(target_url)

                try:
                    WebDriverWait(self.browser, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#inventorylimiteds"))
                    )
                    self.scroll_to_bottom()
                    return True

                except Exception as e:
                    print("Timed out rolimons", e)
                    self.change_proxy()

                print("Cant load rolimons..")
                return False

    def filter_inventory(self, inventory_dict, applyNFT=False):
        filtered_keys = []
        for uaid, info in inventory_dict.items():
            # Check if the item is on hold or if it's in the NFR list
            if info['on_hold'] == True or info['item_id'] in self.config.load_trading()['NFR'] and applyNFT == False:
                filtered_keys.append(uaid)
            if info['item_id'] in self.config.load_trading()['NFT'] and applyNFT == True:
                filtered_keys.append(uaid)

        return filtered_keys

    def get_profile_data(self, user_id, filter_NFT=False):
        """
        Checks the timer on the website and returns relevant data.
        """
        target_url =  f"https://www.rolimons.com/player/{user_id}"
        inventory_dict = {}
        load_page = self.load_rolimons_page(target_url)
        if load_page == False:
            print("Failed to load page")
            return False
        time.sleep(.1)

        # Get all the children on the item html
        elements = self.browser.find_elements(By.CSS_SELECTOR, "#mix_container *") 

        item_id = None
        uaid = None
        is_on_hold = False
        date = None
        held_uaids = []

        last_item_id = None
        last_uaid = None

        for element in elements:

            # Check if the element is a link
            if element.tag_name == 'a':
                href = element.get_attribute("href")
                text = element.text.strip()
                if "www.rolimons.com/item/" in href:
                    item_id = href.split('/')[-1]

                if  "www.rolimons.com/uaid/" in href:
                    uaid = href.split('/')[-1]
                    #print(uaid)

                if "Owner Since" in text: 
                    date = self.parse_time_ago_to_epoch(str(text))

            if element.get_attribute("class") == "hold_item_tag_icon hold_tag_icon":
                is_on_hold = True

            # Dont flag as trade locked because the UAID of the item is nested in multiple copies
            if element.get_attribute("class") == "item-hold-quantity copies_on_hold":
                is_on_hold = False

            # Append multiple trade locked UAIDs that is nested into the same item
            if element.tag_name == 'svg':
                parent_link = element.find_element(By.XPATH, '..')  # '..' selects the parent element
                on_hold_uaid = parent_link.get_attribute("href").split('/')[-1]
                held_uaids.append(on_hold_uaid)

            if uaid != last_uaid and date:
                inventory_dict[uaid] = {"item_id": item_id, "on_hold": is_on_hold, "timestamp": date}
                #print(item_id, uaid, date, is_on_hold, held_uaids)
                is_on_hold = False
                uaid = None

        for uaid in held_uaids:
            inventory_dict[uaid]['on_hold'] = True

        filtered_keys = self.filter_inventory(inventory_dict, filter_NFT)
        for uaid in filtered_keys:
            del inventory_dict[uaid]
        return inventory_dict


  
    
