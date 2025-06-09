import pyotp
import time
import json
from handler.handle_logs import log


class AuthHandler:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AuthHandler, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, cookie: dict = None):
        if self.__initialized:
            return

        self.is_ratelimited = False

    def verify_auth_secret(self, auth_secret):
        try:
            totp = pyotp.TOTP(auth_secret)
            totp.now()
        except ValueError:
            return False
        except Exception as e:
            log(f"error for verify auth {e}")
            return False
        return True

    def verify_request(self, req_handler, user_id, metadata_challenge_id, auth_generator):
        """
        Verify 2FA request for a user using TOTP authenticator.

        Args:
            req_handler: Request handler with session and headers
            user_id: User ID for verification
            metadata_challenge_id: Challenge ID from metadata
            auth_generator: TOTP generator for auth codes

        Returns:
            str: Verification token on success
            bool: False on failure
        """
        log(f"Starting 2FA verification for user {user_id}")

        max_retries = 10  # Prevent infinite loops
        retry_count = 0

        while retry_count < max_retries:
            # Check rate limit status
            if self.is_ratelimited:
                log(f"Rate limited, waiting 1 second (attempt {
                    retry_count + 1})")
                time.sleep(1)
                retry_count += 1
                continue

            try:
                # Make 2FA verification request
                response = req_handler.Session.post(
                    f"https://twostepverification.roblox.com/v1/users/{
                        user_id}/challenges/authenticator/verify",
                    headers=req_handler.headers,
                    json={
                        "actionType": "Generic",
                        "challengeId": metadata_challenge_id,
                        "code": auth_generator.now()
                    }
                )

                # Success case
                if response.status_code == 200:
                    log(f":AUTH STATUS HERE: {response.text}\n{
                        response.json()}\n{response.headers}", dontPrint=True)
                    try:
                        verification_token = response.json().get("verificationToken")
                        if verification_token:
                            log(f"Successfully obtained verification token for user {
                                user_id}")
                            return verification_token
                        else:
                            log(f"No verification token in response for user {
                                user_id}")
                            return False
                    except (KeyError, ValueError) as e:
                        log(f"Failed to parse successful response: {e}")
                        return False

                # Handle error responses
                if response.status_code == 429:
                    log(f"Rate limit hit, waiting 75 seconds for user {
                        user_id} {response.text} {response.url}")
                    self.is_ratelimited = True
                    time.sleep(75)
                    self.is_ratelimited = False
                    retry_count += 1
                    continue

                # Handle other errors with JSON response
                try:
                    error_data = response.json()
                    if "errors" in error_data:
                        errors = error_data["errors"]

                        # Check for "Authenticator code already used" error
                        if any(error.get("code") == 18 for error in errors):
                            log(f"Authenticator code already used for user {
                                user_id}, waiting 30 seconds")
                            time.sleep(30)
                            retry_count += 1
                            continue

                        # Challenge is required to authorize the request
                        if any(error.get("code") == 0 for error in errors):
                            continue

                        # Log other errors and wait
                        log(f"2FA error for user {user_id}: {error_data}")
                        time.sleep(120)
                        return False
                    else:
                        log(f"Unexpected error response format: {error_data}")
                        return False

                except (ValueError, KeyError):
                    # Non-JSON response or missing expected fields
                    log(f"Non-JSON error response: {
                        response.text} (status: {response.status_code})")
                    req_handler.generate_csrf()
                    retry_count += 1
                    continue

            except Exception as e:
                log(f"Request failed with exception: {e}", severity_num=2)
                retry_count += 1
                time.sleep(5)  # Brief pause before retry
                continue

        log(f"2FA verification failed after {
            max_retries} attempts for user {user_id}")
        return False

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
        return response
