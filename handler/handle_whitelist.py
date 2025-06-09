import requests
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from handler.handle_logs import log


import sys
from Crypto.PublicKey import *
from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA
import base64
from Crypto.Hash import SHA256
import json
import traceback
import uuid
from datetime import datetime, timezone
import time


TRUST_PUB_KEY = """
LS0tLS1CRUdJTiBSU0EgUFVCTElDIEtFWS0tLS0tCk1JSUJDZ0tDQVFFQXNGRjFMN3VNcGhwK
3RuUmRYd0NOdThrK3Q1T0pFa0FOUkFtM0lPcTZCQU9MR21pMWJ3THQKWGpTT05sZHA5VFFBWE
R4STVJVG5OcEJNZ08yYjlnV1lhUXJiSnVvNDVPNFFmTk9XT0Z0bTIwQXJ3ejRQTjRydApYS2V
2Z1NhOEV1Yml1Tmc2NjRrbXRjQldrRTh0dzFCK1dNcVZWelcwa2NGbXJRdEZ6WlRsM2RtQWdI
djJzNjY0CjNQSnY5QURGMjFUbm5keDZ6U0RHd09VejNLTFJmaTJobmthZlhyS2hkV1UySHEyM
E53ODUvSzh0UGZ4SGRuanIKTGxWYWZVcUNYWkd4eVkyTlF1UG9MRVcraEFQMXdFUWpmQlc1dT
N3bkxXTWRHVitEd0JHUnFucCtlQlowUDlwNwphcVU0S2NXRGFDRkxSZlM3Q1J4N2VSV0kwWXd
wMGY4Qk53SURBUUFCCi0tLS0tRU5EIFJTQSBQVUJMSUMgS0VZLS0tLS0K
"""

VERSION = "1.0V"


class Whitelist():
    def __init__(self):
        self.req = requests.Session()

        self.RSAGenerator = RSA
        self.req.trust_env = False
        self.server_pub_key = None
        self.client_pub = None
        self.client_priv = None

    def get_machine_uuid(self):
        return uuid.UUID(int=uuid.getnode())

    def refresh_keys(self):
        try:
            self.server_pub_key = self.fetch_server_pub_key()
            self.client_pub, self.client_priv = self.client_generate_key_pair()
            self.req.cookies['client_public_key'] = self.client_pub
        except Exception as e:
            raise ValueError(f"Couldnt get whitelist keys: {e}")

    def client_generate_key_pair(self):
        """
        Generates and returns an RSA key pair (public key and private key).
        Encodes the public key in Base64 for safe transport.
        """
        # Generate RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Get private key in PEM format
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Get public key in PEM format
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # Base64 encode both keys
        public_key_b64 = base64.b64encode(public_key_pem).decode()
        private_key_b64 = base64.b64encode(private_key_pem).decode()

        return public_key_b64, private_key_b64

    def sign_with_private_key(self, private_key_b64, message: str):
        """
        Signs the message using the private key and returns a base64-encoded signature.
        """
        # Decode the private key from Base64
        private_key_bytes = base64.b64decode(private_key_b64)

        # Load the private key into an RSA key object
        private_key = load_pem_private_key(private_key_bytes, password=None)

        # Sign the message using PKCS1v15 padding
        signature = private_key.sign(
            message,  # Ensure the message is encoded as bytes
            padding.PKCS1v15(),  # Use PKCS1v15 padding
            hashes.SHA256()  # Use SHA256 hash algorithm
        )

        return base64.b64encode(signature).decode('utf-8')

    def verify_signature(self, public_key, message, signature_base64) -> bool:
        """
        Uses the public key to verify the signature sent by a private key and returns true or false
        """
        # Decode the base64-encoded signature
        signature = base64.b64decode(signature_base64)

        # Step 1: Hash the original message using SHA-256
        message_hash = hashes.Hash(hashes.SHA256(), backend=default_backend())
        message_hash.update(message)
        expected_hash = message_hash.finalize()

        # Step 2: Verify the signature using the public key
        try:
            # Decrypt the signature using the public key (this gives the original hash)
            public_key.verify(
                signature,
                message,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

            return True
        except Exception as e:
            return False

    def decrypt_with_private_key(self, response):
        """
        Decrypts the encryptedData from a response and returns it decoded
        """
        # Decode the private key from Base64
        json = None
        try:
            json = response.json()['encryptedData']
        except:
            try:
                log(response.text, severityNum=3)
            except:
                pass
            log("Failed to get encrypted data from response",
                severityNum=3, dontPrint=True)
            time.sleep(3)
            return None

        private_key_bytes = base64.b64decode(self.client_priv)
        private_key = RSA.import_key(private_key_bytes)

        # Create a cipher object using the private key (with SHA-256 for OAEP)
        cipher = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)

        # Decode the encrypted message from Base64
        encrypted_data = base64.b64decode(json)

        # Decrypt the message
        try:
            decrypted_data = cipher.decrypt(encrypted_data)
            # Assuming the message is UTF-8 encoded
            return decrypted_data.decode('utf-8')
        except ValueError as e:
            log(f"Decryption failed: {e}")
            time.sleep(3)
            return None

    def encrypt_with_public_key(self, message: str):
        """
        Encrypts message and returns base64 encoded message
        """
        encrypted_message = self.server_pub_key.encrypt(
            message,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return base64.b64encode(encrypted_message).decode('utf-8')

    def fetch_server_pub_key(self):
        """
        Requests server API for the public key and returns it as a public key object
        """
        # TODO: VERIFY VERSION
        publicKeyAPI = "http://www.doggotradebot.xyz/public-key"
        response = self.req.get(publicKeyAPI)

        if 'server_public_key' not in self.req.cookies.keys():
            log("Public key not found, cannot begin authorization.")
            time.sleep(3)
            return False

        try:
            public_cookie = self.req.cookies['server_public_key']
            public_key_der = base64.b64decode(public_cookie)
            server_public_key = serialization.load_der_public_key(
                public_key_der)
        except:
            log("Couldnt get server public key")
            time.sleep(3)
            return False

        return server_public_key

    def register_user(self, username: str, password: str, orderid: str) -> bool:
        '''
            Uses the Register API to generate a new user in the database
            OrderID   string    `json:"orderid"`
            Username  string    `json:"username"`
            Password  string    `json:"password"`
            IPAddress string    `json:"ip_address"`
            Version   string    `json:"version"`
            Hwid      string    `json:"hwid"`
        '''

        try:
            # NOTE: REFRESH KEYS AFTER POSTING THE API
            self.refresh_keys()
            hwid = self.get_machine_uuid()
            send_data = f'{{"username": "{username}", "password": "{password}", "orderid": "{
                orderid}", "hwid": "{hwid}", "version": "{VERSION}"}}'.encode('utf-8')

            encrypted_data = self.encrypt_with_public_key(send_data)
            signature_base64 = self.sign_with_private_key(
                self.client_priv, send_data)

            while True:
                try:
                    response = self.req.post("https://www.doggotradebot.xyz/register", json={
                                             'encryptedData': encrypted_data, 'sig': signature_base64}, verify=True)
                    break
                except:
                    log("Failed to contact whitelist API retrying")
                    time.sleep(1)

            if response.status_code == 200:

                if response.json().get('sig') and response.json().get('trust'):
                    if not self.verify_signature(self.server_pub_key, send_data, response.json()['sig']):
                        return False                # Verify hard coded keys

                    try:
                        pub_key_pem = base64.b64decode(TRUST_PUB_KEY)
                        trust_public_key = serialization.load_pem_public_key(
                            pub_key_pem, backend=default_backend())
                    except Exception as e:
                        log(f"Couldnt get server public trust key {
                            e}", severityNum=3)
                        time.sleep(3)
                        return False

                    if not self.verify_signature(trust_public_key, send_data, response.json()['trust']):
                        return False

                    decrypted_response = self.decrypt_with_private_key(
                        response)
                    decrypted_json = json.loads(decrypted_response)
                    if not decrypted_json.get("nonce"):
                        log("invalid data non")
                        return False

                    timestamp_str = decrypted_json["nonce"][:26]
                    timestamp = datetime.fromtimestamp(
                        # Use timezone.utc for UTC
                        int(timestamp_str[:-1]), timezone.utc)
                    unix_timestamp = int(timestamp.timestamp())

                    if (abs(unix_timestamp) - time.time()) > 600:
                        log("Nonce out of date")
                        return False

                    if decrypted_json.get("registered"):
                        if decrypted_json['registered'] == 'true':
                            log("User Registered!")
                            return True
                        else:
                            log("User not Registered")
                            return False
                else:
                    if 'encryptedData' in response.text:
                        log(f"Got Registering whitelist: {self.decrypt_with_private_key(response)} URL: {
                            response.url} Status Code: {response.status_code}", severityNum=3)
                    else:
                        log(f"Got Registering from whitelist {response.text}, URL: {
                            response.url} Status Code: {response.status_code}", severityNum=3)

                    # let people read
                    time.sleep(6)
            return False

        except Exception as e:
            tb = traceback.format_exc()  # Capture the full traceback
            log(f"{e, tb}", severityNum=4)
            return False

    def send_whitelist_post(self, username: str, password: str, orderid: str, url: str):
        """
        Encrypts use data and sends the whitelist API and then returns the response
        """
        # NOTE: REFRESH KEYS AFTER POSTING THE API
        self.refresh_keys()
        hwid = self.get_machine_uuid()
        message = f'{{"username": "{username}", "password": "{password}", "orderid": "{
            orderid}", "hwid": "{hwid}", "version": "{VERSION}"}}'.encode('utf-8')

        signature_base64 = self.sign_with_private_key(
            self.client_priv, message)
        encrypted_message_base64 = self.encrypt_with_public_key(message)

        try:
            while True:
                try:
                    response = self.req.post(
                        url, json={'encryptedData': encrypted_message_base64, 'sig': signature_base64})
                    break
                except:
                    log("Whitelist API not responding retrying")
                    time.sleep(1)

            if response.status_code != 200:
                if 'encryptedData' in response.text:
                    decrypted = self.decrypt_with_private_key(response)
                    if "expired" in decrypted:
                        log("Retrying")
                        self.send_whitelist_post(
                            username, password, orderid, url)

                    log(f"Got error from whitelist: {decrypted} URL: {
                        response.url} Status Code: {response.status_code}", severityNum=3)
                    time.sleep(5)
                    return False, False
                else:
                    if "Mismatch" in response.text:
                        log("Version mismatch, please update to the latest version of doggo.", severityNum=4)
                        time.sleep(5)
                        sys.exit(0)

                    log(f"Got error from whitelist {response.text}, URL: {
                        response.url} Status Code: {response.status_code}", severityNum=3)
                # let people read
                time.sleep(5)
        except Exception as e:
            log(f"{e} ERROR post whitelist {url}", severityNum=3)
            return False, False

        return response, message

    def reset_ip(self, username, password, orderid) -> bool:
        response, message_sent = self.send_whitelist_post(
            username, password, orderid, "https://www.doggotradebot.xyz/reset-ip")

        if not response:
            try:
                decrtyped_response = self.decrypt_with_private_key(response)
                log(decrtyped_response)
            except:
                log(response, severityNum=3)
                pass

            return False

        if response.status_code == 200:
            log("Successfully resetIP")
            return True

    def is_valid(self, username, password, orderid) -> bool:
        """
        returns a bool wether or not the username and password got an ok from the server and then generates new keys
        """
        try:
            response, message_sent = self.send_whitelist_post(
                username, password, orderid, "https://www.doggotradebot.xyz/login")

            if response == False:
                log("Coudlnt contact whitelist API")
                return False

            if response.status_code == 200:
                decrtyped_response = self.decrypt_with_private_key(response)
                if decrtyped_response is None:
                    log(f"Got error for login API {
                        response.text}", severityNum=3)
                    time.sleep(3)
                    return False

                response_json = response.json()
                signature_base64 = response_json.get('sig')
                trusted_sig = response_json.get('trust')

                # Verify hard coded keys
                try:
                    pub_key_pem = base64.b64decode(TRUST_PUB_KEY)
                    trust_public_key = serialization.load_pem_public_key(
                        pub_key_pem, backend=default_backend())
                except Exception as e:
                    log(f"Couldnt get server public trust key {
                        e}", severityNum=3)
                    return False

                # NOTE: VERIFY THE REQUEST
                if not trusted_sig:
                    return False

                if not signature_base64:
                    return False

                if not self.verify_signature(trust_public_key, message_sent, trusted_sig):
                    return False

                if not self.verify_signature(self.server_pub_key, message_sent, signature_base64):
                    return False

                decrypted_json = json.loads(decrtyped_response)
                if not decrypted_json.get("nonce"):
                    log("invalid data non")
                    return False

                timestamp_str = decrypted_json["nonce"][:26]
                timestamp = datetime.fromtimestamp(
                    # Use timezone.utc for UTC
                    int(timestamp_str[:-1]), timezone.utc)
                unix_timestamp = int(timestamp.timestamp())

                if (abs(unix_timestamp) - time.time()) > 600:
                    log("Nonce out of date")
                    return False

                if decrypted_json.get("success"):
                    if decrypted_json['success'] == "ok":
                        return True

        except Exception as e:
            tb = traceback.format_exc()  # Capture the full traceback

            log(f"{e}, {tb}", severityNum=3)
            return False
