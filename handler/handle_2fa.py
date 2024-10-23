import pyotp
import time

class AuthHandler:
    def __init__(self):
        # Get cookie and the auth for that cookie
        pass

    def authenticate(self):
        # return the auth code for that cookie
        pass

    def verify_auth_key(self, auth_secret):
        try:
            self.authenticator = pyotp.TOTP(auth_secret)
            self.authenticator.now()
            return self.authenticator
        except:
            print("Couldnt get auth")
            raise ValueError("Authentication failed..")

