import pyotp
import time
import requests
import json
class AuthHandler:
    def __init__(self):
        # Get cookie and the auth for that cookie
        pass

    def get_totp(self, auth_secret):
        totp = pyotp.TOTP(auth_secret)
        return totp.now()


    def verify_request(self, req_handler, user_Id, metadata_challengeId, auth_code):
        print("trying to verify 2fa")
        request = req_handler.Session.post("https://twostepverification.roblox.com/v1/users/" + user_Id + "/challenges/authenticator/verify", headers=req_handler.headers, json={
            "actionType": "Generic",
            "challengeId": metadata_challengeId,
            "code": auth_code
        })

        if "errors" in request.json():
            print("2fa error")
            print(request.json())
            #input(request.json()["errors"][0]["message"])
            return False
        return request.json()["verificationToken"]

    def continue_request(self, req_handler, challengeId, verification_token, metadata_challengeId):
        response = req_handler.Session.post("https://apis.roblox.com/challenge/v1/continue", headers=req_handler.headers, json={
            "challengeId": challengeId,
            "challengeMetadata": json.dumps({
                "rememberDevice": True,
                "actionType": "Generic",
                "verificationToken": verification_token,
                "challengeId": metadata_challengeId
            }),
            "challengeType": "twostepverification"
        })
        print(response.text, "AUTHNCTIACTION!!!")
