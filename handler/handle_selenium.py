import os
import re
import time
from datetime import datetime, timedelta
from selenium import webdriver

from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from webdriver_manager.firefox import GeckoDriverManager
import roblox_api
from handler.handle_config import ConfigHandler
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, ElementNotInteractableException


from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromiumService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# TODO: maybe use https://api.rolimons.com/players/v1/playerassets/1283171278 API and use playerPrivacyEnabled instead of can trade
class Chrome:
    """
    Handles all Selenium settings and has methods to fetch data.
    """
    def __init__(self, debugMode=False, proxies=None):
        #TODO: read proxies.txt but add after I make the proxy formatter
        self.proxies = proxies or []  # List of proxies to use
        self.current_proxy_index = 0  # Index to track current proxy
        self.proxy_cooldown = {}  # Dictionary to track cooldown status of proxies

        self.roblox_parse = roblox_api.RobloxAPI()
        self.config = ConfigHandler('config.cfg')
        

        # Setup Chrome options
        self.chrome_options = ChromeOptions()
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument(f'user-agent={user_agent}')
        self.chrome_options.add_argument('--incognito')  # Incognito mode

        self.initialize_browser()


    """
        Base Selenium Functions to setup the browser, load the page and use proxies
    """
    def initialize_browser(self):
        """Initializes the Firefox browser with the current proxy if available."""
        proxy = self.get_current_proxy()
        if proxy:
            self.chrome_options.add_argument(f'--proxy-server=http://{proxy}')

        self.browser = webdriver.Chrome(service=ChromiumService(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()), options=self.chrome_options)
        # Launch the Firefox driver
        #self.browser = webdriver.Firefox(
        #    service=FirefoxService(GeckoDriverManager().install()),
        #    options=self.firefox_options
        #)

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
        
        if time_str.lower() == "just now":
            return int(now.timestamp())
        
        # Clean the input string by removing extra spaces
        time_str = time_str.replace('\n', ' ').strip()

        if "Awaiting" in time_str:
            return int(now.timestamp())

        try:
            # Adjusted regex pattern to match leading text followed by time description (including minutes)
            pattern = r'.*(\d+)\s*(day|days|month|months|year|years|hour|hours|minute|minutes)\s*ago'
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
        elif unit.startswith('minute'):
            target_time = now - timedelta(minutes=value)
        else:
            raise ValueError("Unsupported time unit")

        return int(target_time.timestamp())


    def scroll_to_bottom(self):
        last_height = self.browser.execute_script("return document.body.scrollHeight")
        while True:
            self.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load page
            #time.sleep(.5)

            # Calculate new scroll height and compare with last scroll height
            new_height = self.browser.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    """
        Functions to scrape the rolimons player website
    """

    def load_rolimons_page(self, target_url):
        if self.browser.current_url != target_url:
            max_attemps = 10
            for attemp in range(max_attemps):
                self.browser.get(target_url)

                try:
                    # Use WebDriverWait with the custom function
                    WebDriverWait(self.browser, 30).until(
                        lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#mix_container *")) > 4
                    )

                    self.scroll_to_bottom()
                    return True

                except Exception as e:
                    print("Timed out rolimons", e)
                    self.change_proxy()

                print("Cant load rolimons..")
                return False

    def filter_inventory(self, inventory_dict, applyNFT=False):
        """
        Filters the inventory based on the configuration settings.

        Parameters:
        - inventory_dict (dict): The inventory data to filter.
        - applyNFT (bool): Whether to apply the NFT filter.

        Returns:
        - filtered_keys (list): A list of keys filtered out from the inventory.
        """
        filtered_keys = []
        trading_config = self.config.load_trading()
        not_for_recieve = trading_config['NFR']
        not_for_trade = trading_config['NFT']

        for uaid, info in inventory_dict.items():
            item_id = info['item_id']
            

            #TODO: allow trade projecteds
            #if self.roblox_parse.is_projected(item_id) == True:
            #    filtered_keys.append(uaid)

            # Check if the item is on hold or if it's in the NFR list
            if applyNFT:
                if item_id in not_for_recieve or item_id in not_for_trade:
                    filtered_keys.append(uaid)

        return filtered_keys

    def get_profile_data(self, user_id, filter_NFT=False):
        # TODO: make it readable
        target_url = f"https://www.rolimons.com/player/{user_id}"
        load_page = self.load_rolimons_page(target_url)
        
        if not load_page:
            print("Failed to load page")
            return False

        def find_element(item, search_element, method=By.CSS_SELECTOR, timeout=.5):
            try:
                # Wait for the specific element inside each `item` container
                return WebDriverWait(item, timeout).until(
                    EC.presence_of_element_located((method, search_element))
                )
                # Now you can interact with inner_element here
            except:
                return False

        def find_elements(item, element):
            try:
                return item.find_elements(By.CSS_SELECTOR, element)
            except:
                return False

        def scroll_and_click(element):
            try:
                self.browser.execute_script("arguments[0].scrollIntoView();", element)
                element.click()
            except ElementClickInterceptedException:
                print("Element is obscured; attempting to close overlay.")
                return False

        def scrape_nested_items(nested_element, item_id):
            scraped_data = {}

            for element in nested_element:
                is_on_hold = find_element(element, ".//*[name()='svg' and @aria-hidden='true']", method=By.XPATH)
                if is_on_hold:
                    print("on hold")
                    continue

                uaid = element.get_attribute("href").split("/uaid/")[-1]
                date = element.get_attribute("data-original-title")
                print(item_id, uaid, date)
                scraped_data[uaid] = {"item_id": item_id, "owner_since": self.parse_time_ago_to_epoch(date)}

            return scraped_data

        # Using CSS Selectors to get the desired elements
        item_containers = self.browser.find_elements(By.CSS_SELECTOR, "#mix_container .pb-2.mb-3.mix_item.shadow_md_35.shift_up_md")
        
        # nested items (duplicate items)
        reveal_css = ".btn.btn-bricky-green.border-primary.btn-sm.btn-very-sharp"
        nested_items = ".btn.btn-light-blue.border-primary.btn-sm.btn-very-sharp.uaid_list_button"

        # single items
        hold_tag = ".hold_item_tag_icon.hold_tag_icon"
        date_tag = ".inv_owner_since_time.text-success.text-truncate"


        scanned_inventory = {}
        for item in item_containers:
            multiple_items = find_element(item, reveal_css)
            item_href = find_element(item, "a[href*='/item/']")
            item_id = item_href.get_attribute("href").split("/item/")[-1]

            if multiple_items: 
                click = scroll_and_click(multiple_items)
                if click == False:
                    self.close_modal(item)
                    scroll_and_click(multiple_items)
                nested_info = find_elements(item, nested_items)
                if nested_info:
                    scraped = scrape_nested_items(nested_info, item_id)
                    scanned_inventory.update(scraped)
                self.close_modal(item)
            else:
                is_on_hold = find_element(item, hold_tag)
                if is_on_hold:
                    continue



                uaid_href = find_element(item, "a[href*='/uaid/']")
                uaid = uaid_href.get_attribute("href").split("/uaid/")[-1]

                date = find_element(item, ".inv_owner_since_time.text-success.text-truncate")

                if date == '':
                    print("empty date", uaid, item_id, user_id)
                    date = "99 days ago"
                scanned_inventory[uaid] = {"item_id": item_id, "owner_since": self.parse_time_ago_to_epoch(date.text)}

        filtered_keys = self.filter_inventory(scanned_inventory, filter_NFT)

        for uaid in filtered_keys:
            del scanned_inventory[uaid]
        print(scanned_inventory)
        self.browser.close()
        return scanned_inventory



    def close_modal(self, item):
        try:
            time.sleep(.3) # .25
            close_button = item.find_element(By.CSS_SELECTOR, ".modal-header .close")
            close_button.click()  # Click the close button
            time.sleep(.3)  # Wait for the modal to close

            # Wait for the modal to disappear
            #WebDriverWait(self.browser, 10).until(EC.invisibility_of_element(close_button))
        except NoSuchElementException:
            print("Close button not found.")
        except Exception as e:
            print(f"An error occurred while trying to close the modal: {e}")

