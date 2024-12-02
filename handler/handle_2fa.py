import pyotp
import time
import requests
import json

class AuthHandler:
    def __init__(self):
        # Get cookie and the auth for that cookie
        pass

    def verify_auth_secret(self, auth_secret):
        try:
            totp = pyotp.TOTP(auth_secret)
            secret = totp.now()
        except ValueError:
            return False
        except Exception as e:
            print("error for verify auth", e)
            return False

        return True


    def verify_request(self, req_handler, user_Id, metadata_challengeId, auth_generator):
        while True:
            print(auth_generator.now(), user_Id)
            request = req_handler.Session.post("https://twostepverification.roblox.com/v1/users/" + user_Id + "/challenges/authenticator/verify", headers=req_handler.headers, json={
                "actionType": "Generic",
                "challengeId": metadata_challengeId,
                "code": auth_generator.now()
            })

            
            if "errors" in request.json():
                if request.status_code == 429:
                    print("Waiting 75 seconds for 2fa ratelimit", request.text)
                    time.sleep(75)
                    continue
                

                print("2fa error, waiting 120 seconds")
                print(request.json())
                time.sleep(120)
                #input(request.json()["errors"][0]["message"])
                return False
            try:
                return request.json()["verificationToken"]
            except:
                req_handler.generate_csrf()
                print("error returning verification token", request.text, request.status_code)
                continue

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
        print("continue auth = ", response.text)
