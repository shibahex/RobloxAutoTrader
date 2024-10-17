import pyotp
import time

class Handle2FA:
    def __init__(self):
        # Get cookie and the auth for that cookie
        pass

    def authenticate(self):
        # return the auth code for that cookie
        pass
totp = pyotp.TOTP("2K2UFB2DH4AE3HTPZBMKU3IZQI")
print(totp.now())
