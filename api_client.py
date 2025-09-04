import requests
import time
import base64
import json

class APIClient:
    def __init__(self, base_url, email, password):
        self.base_url = base_url
        self.email = email
        self.password = password
        self.token = None
        self.token_expiry = 0  # epoch timestamp

    def _decode_jwt_exp(self, token):
        """Decode JWT expiry if available"""
        try:
            # JWT format: header.payload.signature
            payload = token.split(".")[1]
            # Fix padding for base64
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            return decoded.get("exp", 0)
        except Exception:
            return 0

    def login(self):
        """Authenticate and store token + expiry"""
        login_url = f"{self.base_url}/login"
        payload = {"email": self.email, "password": self.password}
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": "PostmanRuntime/7.39.0"
        }

        response = requests.post(login_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Some APIs return {"token": "...", "expires_in": 3600}
        self.token = data.get("token") or data.get("access_token")
        if not self.token:
            raise ValueError("No token found in login response!")

        # Priority 1: expires_in field
        if "expires_in" in data:
            self.token_expiry = time.time() + int(data["expires_in"]) - 60
        else:
            # Priority 2: decode JWT "exp" claim
            exp = self._decode_jwt_exp(self.token)
            if exp > 0:
                self.token_expiry = exp - 60  # refresh 1 min early
            else:
                # Default fallback = 1 hour
                self.token_expiry = time.time() + 3600 - 60

    def get_headers(self):
        """Return valid auth headers, refresh if needed"""
        if not self.token or time.time() >= self.token_expiry:
            self.login()
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "*/*",
            "Content-Type": "application/json"
        }

    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers()
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    
    def post(self, endpoint, payload):
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers()
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()


