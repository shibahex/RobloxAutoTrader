from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from seleniumwire import webdriver  # Importing seleniumwire's webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import pyotp

class FirefoxLogin:
    """
    Opens the Firefox browser for the user to manually log into a website and captures network logs.
    """
    def __init__(self):
        self.firefox_options = webdriver.FirefoxOptions()
        user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0'
        )

        self.firefox_options.set_preference("general.useragent.override", user_agent)
        self.firefox_options.add_argument('--private')  # Private mode

        self.initialize_browser()

    def initialize_browser(self):
        """Initializes the Firefox browser."""
        self.browser = webdriver.Firefox(
            service=FirefoxService(GeckoDriverManager().install()),
            options=self.firefox_options
        )
    def enter_auth(self, totp_secret):
        while True:
            try:
                # Wait for the modal to be visible
                modal = WebDriverWait(self.browser, 360).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "div.modal.fade.modal-modern.in"))
                )

                code_input = WebDriverWait(modal, 360).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "#two-step-verification-code-input"))
                )
                print("Two-step verification input detected.")
                time.sleep(.1)

                # Generate the TOTP code
                totp = pyotp.TOTP(totp_secret)
                auth_code = totp.now()  # Get the current code

                # Input the auth code into the verification field
                code_input.send_keys(auth_code)
                print(f"Generated Auth Code: {auth_code}")

                # Click the Verify button
                verify_button = modal.find_element(By.CSS_SELECTOR, "button.btn-cta-md[aria-label='Verify']")
                verify_button.click()
                return True
            except Exception as e:
                print(f"Error while waiting for the two-step verification input: {e}")



    def roblox_login(self, totp_secret):
        """Logs in to Roblox and captures network requests."""
        # Open the Roblox login page
        self.browser.get("https://www.roblox.com/login")
        
        # Store the initial URL
        initial_url = self.browser.current_url

        print("Waiting for user to log in...")
        
        # Wait for the user to log in by checking if the URL changes
        while True:
            current_url = self.browser.current_url
            enter_auth = self.enter_auth(totp_secret)
            if enter_auth == True:
                print("Valid Login")
                break

            # Check if the URL has changed from the login page
            if current_url != initial_url:
                print("Login detected. Capturing network requests...")
                break
            
            # Short sleep to prevent busy-waiting
            time.sleep(.35)

        # Capture network logs after login
        for request in self.browser.requests:
            if request.response:
                # Capture specific login requests
                if 'auth.roblox.com/v2/login' in request.url and request.response.status_code == 200:
                    #print(f"Login API URL: {request.url}")
                    #print(f"Method: {request.method}")
                    #print(f"Response Status: {request.response.status_code}")

                    try:
                        response_body = request.response.body.decode('utf-8')
                     #   print(f"Login API Response: {response_body}")

                        # Extract the ticket from the response
                        response_data = json.loads(response_body)
                        print(response_data)
                        time.sleep(60)

                        username = response_data.get("user", {}).get("name", "")
                        user_id = response_data.get("user", {}).get("id", "")
                        ticket = response_data.get("twoStepVerificationData", {}).get("ticket", "")
                        if ticket:
                            roblosecurity_cookie = self.fetch_cookie()

                            if roblosecurity_cookie:
                                return roblosecurity_cookie, username, str(user_id)
                            else:
                                raise ValueError("Failed to login to account.")
                        else:
                            raise ValueError("No ticket found in the response.")

                    except (UnicodeDecodeError, json.JSONDecodeError):
                        print("Error processing the login API response.")
                    
                    #print("-" * 60)

    def fetch_cookie(self):
        timeout = 20
        attempts = 0
        roblosecurity_cookie = None

        while attempts < timeout:
            roblosecurity_cookie = self.browser.get_cookie('.ROBLOSECURITY')
            
            if roblosecurity_cookie:
                return roblosecurity_cookie['value']
            
            time.sleep(.3)
            attempts += 1
        return None

    def stop(self):
        """Shut down the browser."""
        self.browser.close()


