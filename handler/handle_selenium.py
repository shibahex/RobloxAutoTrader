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

    def get_dates(self):
        """
        Checks the timer on the website and returns relevant data.
        """
        inventory_cssSelector = "#mix_container"
        items_cssSelector = '[data-ref="item"]'
        owner_since_cssSelector = ".inv_owner_since_time.text-success.text-truncate"
        uaid_button_cssSelector = ".btn.btn-light-blue.border-primary.btn-sm.btn-very-sharp"
        item_button_cssSelector = ".d-flex.justify-content-between a"

        target_url = "https://www.rolimons.com/player/2744514142"  
        
        while True:
            if self.browser.current_url != target_url:
                self.browser.get(target_url)
                # Wait until the inventory container is present
                WebDriverWait(self.browser, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, inventory_cssSelector))
                )

            # Retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    inventory_element = self.browser.find_element(By.CSS_SELECTOR, inventory_cssSelector)
                    item_elements = inventory_element.find_elements(By.CSS_SELECTOR, items_cssSelector)

                    for element in item_elements:
                        try:
                            owner_since_element = element.find_element(By.CSS_SELECTOR, owner_since_cssSelector)
                            uaid_button = element.find_element(By.CSS_SELECTOR, uaid_button_cssSelector)
                            uaid_href = uaid_button.get_attribute('href')
                            item_button = element.find_element(By.CSS_SELECTOR, item_button_cssSelector)
                            item_href = item_button.get_attribute('href')

                            print(owner_since_element.text, item_href.split("/")[-1], uaid_href.split("/")[-1])
                            timestamp = self.parse_time_ago_to_epoch(owner_since_element.text)
                            print(timestamp)

                        except NoSuchElementException:
                            print("Owner since time element not found for one of the items.")
                        except ValueError as e:
                            print(f"Failed getting rolimons inventory: {e}")

                    return  # Exit the function after successfully getting dates

                except WebDriverException as e:
                    if '404' in str(e):
                        print("Received 404 error, changing proxy...")
                        self.change_proxy()
                        break  # Break to reattempt with the new proxy
                    elif '429' in str(e):
                        print("Received 429 error, waiting for 60 seconds...")
                        time.sleep(60)  # Wait before retrying
                    else:
                        print(f"An unexpected error occurred: {e}")
                        break  # Exit on other errors

                time.sleep(1)  # Small delay before the next attempt


