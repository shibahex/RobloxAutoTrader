import binascii
import pyotp
import time
import json
import requests
from handler.handle_logs import log
from handler.exceptions_types import TwoFactorError, parse_roblox_errors


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
        except (ValueError, TypeError, binascii.Error) as e:
            log(f"Invalid auth secret: {e}")
            return False
        return True

    def verify_request(
        self, req_handler, user_id, metadata_challenge_id, auth_generator
    ) -> str:
        """
        Verify 2FA request for a user using TOTP authenticator.

        Returns the verification token.
        Raises TwoFactorError if Roblox refuses the code or retries run out.
        """
        log(f"Starting 2FA verification for user {user_id}")

        max_retries = 10  # Prevent infinite loops
        retry_count = 0
        last_problem = "no attempts made"

        while retry_count < max_retries:
            # Another thread is backing off from a 2FA rate limit. Wait it out
            # (up to 90s) without using up our own attempts.
            waited = 0
            while self.is_ratelimited and waited < 90:
                time.sleep(1)
                waited += 1

            retry_count += 1

            try:
                response = req_handler.Session.post(
                    f"https://twostepverification.roblox.com/v1/users/{user_id}/challenges/authenticator/verify",
                    headers=req_handler.headers,
                    json={
                        "actionType": "Generic",
                        "challengeId": metadata_challenge_id,
                        "code": auth_generator.now(),
                    },
                    timeout=30,
                )
            except requests.RequestException as e:
                last_problem = f"network error: {e}"
                log(f"2FA request failed: {e}", severityNum=2)
                time.sleep(5)
                continue

            if response.status_code == 200:
                try:
                    verification_token = response.json().get("verificationToken")
                except ValueError as e:
                    raise TwoFactorError(
                        f"2FA verify returned invalid JSON for {user_id}: {e}"
                    ) from e
                if not verification_token:
                    raise TwoFactorError(
                        f"No verification token in 2FA response for {user_id}"
                    )
                log(f"Successfully obtained verification token for user {user_id}")
                return verification_token

            if response.status_code == 429:
                last_problem = "rate limited"
                log(f"2FA rate limit hit, waiting 75 seconds for user {user_id}")
                self.is_ratelimited = True
                try:
                    time.sleep(75)
                finally:
                    self.is_ratelimited = False
                continue

            if (
                response.status_code == 403
                and "x-csrf-token" in response.headers
                and response.headers["x-csrf-token"]
                != req_handler.headers.get("x-csrf-token")
            ):
                last_problem = "csrf token refreshed"
                req_handler.headers["x-csrf-token"] = response.headers["x-csrf-token"]
                continue

            codes = [code for code, _ in parse_roblox_errors(response)]
            last_problem = f"{response.status_code} {response.text[:200]}"

            # Authenticator code already used, wait for the next one
            if 18 in codes:
                log(
                    f"Authenticator code already used for {user_id}, waiting 30 seconds"
                )
                time.sleep(30)
                continue

            # Challenge is required to authorize the request; try again
            if 0 in codes:
                time.sleep(2)
                continue

            if not codes:
                # Not a Roblox error body, often a stale csrf token
                req_handler.generate_csrf()
                continue

            raise TwoFactorError(
                f"2FA refused for user {user_id} (check the auth secret and system clock): {last_problem}"
            )

        raise TwoFactorError(
            f"2FA verification failed after {max_retries} attempts for {user_id}: {last_problem}"
        )

    def continue_request(
        self, req_handler, challengeId, verification_token, metadata_challengeId
    ):
        try:
            response = req_handler.Session.post(
                "https://apis.roblox.com/challenge/v1/continue",
                headers=req_handler.headers,
                json={
                    "challengeId": challengeId,
                    "challengeMetadata": json.dumps(
                        {
                            "rememberDevice": True,
                            "actionType": "Generic",
                            "verificationToken": verification_token,
                            "challengeId": metadata_challengeId,
                        }
                    ),
                    "challengeType": "twostepverification",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise TwoFactorError(f"2FA continue request failed: {e}") from e

        if response.status_code != 200:
            raise TwoFactorError(
                f"2FA continue request refused: {response.status_code} {response.text[:200]}"
            )
        return response
