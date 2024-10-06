import os
import re
import time
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
        pattern = r'(\d+)\s*(day|days|month|months|year|years)\s*ago'
        match = re.match(pattern, time_str)
        
        if not match:
            raise ValueError("Invalid time format")

        value = int(match.group(1))
        unit = match.group(2)

        now = datetime.now()

        if unit.startswith('day'):
            target_time = now - timedelta(days=value)
        elif unit.startswith('month'):
            target_time = now - timedelta(days=value * 30)  # Approximation
        elif unit.startswith('year'):
            target_time = now - timedelta(days=value * 365)  # Approximation
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


    def get_profile_data(self, user_id):
        """
        Checks the timer on the website and returns relevant data.
        """
        target_url =  f"https://www.rolimons.com/player/{user_id}"
        inventory_dict = {}
        load_page = self.load_rolimons_page(target_url)
        if load_page == False:
            return False
        every_href = self.browser.find_elements(By.XPATH, "//a[@href]")
        # NOTE: THIS ONLY WORKS BECAUSE IT SPAMS ITEM_ID THEN UAID

        item_id = None
        uaid = None
        date = None
        for element in every_href:
            href = element.get_attribute("href")
            text = element.text

            """
                {AssetID: (UAID, Date)}
            """


            if "item/" in href:
                item_id = href.split('/')[-1]

            if  "www.rolimons.com/uaid/" in href:
                uaid = href.split('/')[-1]

            if "Owner Since" in text: 
                date = text.split("\n")[-1]

            if item_id != None and uaid != None and date != None:
                timestamp = self.parse_time_ago_to_epoch(date)
                inventory_dict[uaid] = {"item_id": item_id, "timestamp": timestamp}
                item_id = None
                uaid = None
                date = None

        if inventory_dict == {}:
            return False

        return inventory_dict

