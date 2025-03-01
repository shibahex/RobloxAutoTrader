#from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from seleniumwire import webdriver  # Importing seleniumwire's webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import pyotp
import sys
import os

# TODO: create .network directory if not exists, and clear the data alot also I forgor
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
        # Check if the directory exists
        network_dir = './.network'
        if not os.path.exists(network_dir):
            # Create the directory
            os.makedirs(network_dir)
            if os.name == 'nt':
                os.system(f'attrib +h +s {network_dir}') 

        selenium_wire_dir = os.path.join(network_dir, '.seleniumwire')
        if not os.path.exists(selenium_wire_dir):
            os.makedirs(selenium_wire_dir)

        with open(os.path.join(selenium_wire_dir, "seleniumwire-dhparam.pem"), 'w') as f:
            f.write(dh_pem)

        with open(os.path.join(selenium_wire_dir, "seleniumwire-ca.pem"), 'w') as f:
            f.write(ca_pem)


        # Then use this path for selenium wire options
        self.selenium_wire_options = {
            'request_storage_base_dir': './.network',
            'request_storage': 'memory',
            'request_storage_max_size': 100  # Store no more than 100 requests in memory
        }
        self.initialize_browser()

    def initialize_browser(self):
        """Initializes the Firefox browser."""
        self.browser = webdriver.Firefox(
            service=FirefoxService(GeckoDriverManager().install()),
            options=self.firefox_options,
            seleniumwire_options=self.selenium_wire_options
        )
    def enter_auth(self, totp_secret):
        while True:
            try:
                totp = pyotp.TOTP(totp_secret)
                print("[Debug] Current Auth Code: ", totp.now())
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
        
        try:
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
        finally:
            del self.browser.requests

    def fetch_cookie(self):
        timeout = 30
        attempts = 0
        roblosecurity_cookie = None

        while attempts < timeout:
            roblosecurity_cookie = self.browser.get_cookie('.ROBLOSECURITY')
            
            if roblosecurity_cookie:
                return roblosecurity_cookie['value']
            
            time.sleep(.5)
            attempts += 1
        return None

    def stop(self):
        """Shut down the browser."""
        self.browser.close()

dh_pem = """
-----BEGIN DH PARAMETERS-----
MIICCAKCAgEAyT6LzpwVFS3gryIo29J5icvgxCnCebcdSe/NHMkD8dKJf8suFCg3
O2+dguLakSVif/t6dhImxInJk230HmfC8q93hdcg/j8rLGJYDKu3ik6H//BAHKIv
j5O9yjU3rXCfmVJQic2Nne39sg3CreAepEts2TvYHhVv3TEAzEqCtOuTjgDv0ntJ
Gwpj+BJBRQGG9NvprX1YGJ7WOFBP/hWU7d6tgvE6Xa7T/u9QIKpYHMIkcN/l3ZFB
chZEqVlyrcngtSXCROTPcDOQ6Q8QzhaBJS+Z6rcsd7X+haiQqvoFcmaJ08Ks6LQC
ZIL2EtYJw8V8z7C0igVEBIADZBI6OTbuuhDwRw//zU1uq52Oc48CIZlGxTYG/Evq
o9EWAXUYVzWkDSTeBH1r4z/qLPE2cnhtMxbFxuvK53jGB0emy2y1Ei6IhKshJ5qX
IB/aE7SSHyQ3MDHHkCmQJCsOd4Mo26YX61NZ+n501XjqpCBQ2+DfZCBh8Va2wDyv
A2Ryg9SUz8j0AXViRNMJgJrr446yro/FuJZwnQcO3WQnXeqSBnURqKjmqkeFP+d8
6mk2tqJaY507lRNqtGlLnj7f5RNoBFJDCLBNurVgfvq9TCVWKDIFD4vZRjCrnl6I
rD693XKIHUCWOjMh1if6omGXKHH40QuME2gNa50+YPn1iYDl88uDbbMCAQI=
-----END DH PARAMETERS-----
"""
ca_pem = """
-----BEGIN CERTIFICATE-----
MIIFFzCCAv+gAwIBAgIUIUc6dnnqhYX3ZYXQzpZyJ1gtUwcwDQYJKoZIhvcNAQEL
BQAwGzEZMBcGA1UEAwwQU2VsZW5pdW0gV2lyZSBDQTAeFw0xODA3MjAxMDQxMDNa
Fw0yODA3MTcxMDQxMDNaMBsxGTAXBgNVBAMMEFNlbGVuaXVtIFdpcmUgQ0EwggIi
MA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoICAQDKKpm14AHiJb4onGES4Echs2qB
XsfeMAbsA7x4blJkMGyHGx9B8OpXqlRtcNnWD2JGnjc0/k92uuZaV2prDnZwH5Jl
nJSZuGEzUUAnrwhTHTqMhM9pfT8RpltE0lyplQni8rjH5oshBrzzAHILm/iAm1WI
HCFUClQaJ7sVVzAikaPfg4WUXLHP7/AjxIejp/SVI8Ycn1BPIlDwp1pIq4WawJoZ
TZ75GwvsT1ohH4YSRM+BxwBuBUqjusaYJiWwpnR801XV290i3/bBOkS2fEa4+ciS
LEGEi4SaaC6Nhap3sd80npJUQff4ltVGaxX0jCG/zswf2XGEDtsw2FF848KePj4X
Ilgm4xcuhhBvcsgob/bwEvDTrXPk38YQEJEKH8uGf37AOv2TQmqj45WZt7jSZ2YH
ZGn4RunJAO/J7toqJ7upjx66Pq8WkXQ6faSeTNENmXclYPRQFujVbFkECRcOtS6W
fUkHM+tgXHKqSMcfVVp46o/4HfHzoTyvrUDryHJB3h/IrqWK1433rYp3bJzkpjM9
JT71vh6sDo/Ys+4HK5rwrwkeP7b+6dUx1nHOgPX88njVI6cuxnjex6AfSld5d4BH
YZdviXRqCxpiudmnN+cMKAdJgRZFmVNH/djQqtq3y/gmjwKnyW95y3uJu4Xz5+R4
9jhAZGJFiHK/vE+XwwIDAQABo1MwUTAdBgNVHQ4EFgQUPvrTydSlYhMQJy8lvBvh
nLeQsvQwHwYDVR0jBBgwFoAUPvrTydSlYhMQJy8lvBvhnLeQsvQwDwYDVR0TAQH/
BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAgEAmIvadNtFca9vuMuSewSXHlOd9p7d
9xYkp8Yj5RvFUGL32zYUatH9YsRh5K9Wz5jifjwBLMRDZIm48xhxYjqVvTZoQpL6
Qyzbu2EsRCbmQ+861U4SfcP2uetJuFM6Ug0/CKviyNpUaX/8YWupFXsEiCRJM9pk
sh2b+dqljy9kvrOosfehz8CRbxUfgPsL2IVZa0mHsuOZDa/XHAAW9ns5TdBlFHwo
W/2KDvvPGL/3t7Zah2jwu8D8w397looMXxqyT/DAjH6+bd5Kg/7mELaqbg/pM3EJ
mENd5ButBkhpVbyAKLn7TvpZYSEF/VMNPcZHOKoKrx1utZwLFuVIb07WDMRov0GO
hg/rrIBWvA1ySi/4yrnRDc7GBHSUh0Krx6LLZ/ZtE3j7/4rwj51MwqqNhQrCxGhz
ksqn8V6XY7UUKnlTlAWRyuBLiA+yvf9GdgNJxUblZYMNpPbeLwe2Be/utROuMqwr
G4RA1sfPuEdyfdXB/7c8ViOPxKYFH0POXuwB+Z1JlXDtR8rbjyVPUwqQarAuNIbw
NC8P+GWSzviG544BQyW1xKqLgQcEMSU73icDOOb9COcl1h7URSO9WB6CZXykpQSk
hceDiwojCDsyM84uXyyXKXCRPtseCIRsA1zZwrXU7NDDBXrIC7moVbxkDu2G4V1g
b5JFYe4FNI0yw/o=
-----END CERTIFICATE-----

-----BEGIN PRIVATE KEY-----
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
M4ASYgjl3b4eb4ejEp9ylbMJ/I7G0mU=
-----END PRIVATE KEY-----
"""

