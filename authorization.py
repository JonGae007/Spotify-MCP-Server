import json
import os
import secrets
import time
import webbrowser
import hashlib
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv


TOKEN_FILE = Path(__file__).with_name(".spotify_tokens.json")
REQUIRED_SCOPES = (
    "user-top-read",
    "user-read-recently-played",
)


def load_tokens():
    if not TOKEN_FILE.exists():
        return None

    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_tokens(tokens):
    token_data = dict(tokens)
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    token_data["granted_scopes"] = token_data.get("scope", "").split()
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def refresh_access_token(refresh_token):
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": os.environ["SPOTIFY_CLIENT_ID"],
        },
        timeout=30,
    )
    response.raise_for_status()
    refreshed = response.json()
    refreshed["refresh_token"] = refreshed.get("refresh_token", refresh_token)

    current = load_tokens() or {}
    current.update(refreshed)
    save_tokens(current)
    return current


def get_authorization_code(redirect_uri):
    redirect = urlparse(redirect_uri)
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            result["code"] = query.get("code", [None])[0]
            result["state"] = query.get("state", [None])[0]
            result["error"] = query.get("error", [None])[0]

            success = result["code"] is not None and result["state"] == state
            body = (
                "<h1>Spotify-Zugriff erlaubt</h1>"
                "<p>Du kannst dieses Fenster jetzt schliessen.</p>"
                if success
                else "<h1>Anmeldung fehlgeschlagen</h1>"
                "<p>Du kannst dieses Fenster schliessen.</p>"
            )

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", redirect.port or 80), CallbackHandler)

    params = {
        "client_id": os.environ["SPOTIFY_CLIENT_ID"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "scope": " ".join(REQUIRED_SCOPES),
        "state": state,
    }
    authorization_url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    webbrowser.open(authorization_url)
    print("Bitte erteile der App im Browser die Zustimmung...")

    while not result.get("code") and not result.get("error"):
        server.handle_request()
    server.server_close()

    if result["error"] or result["state"] != state:
        raise RuntimeError(result["error"] or "Ungultiger OAuth-State")
    return result["code"], code_verifier


def get_access_token():
    load_dotenv()

    required = (
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_REDIRECT_URI",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Fehlende Umgebungsvariablen: " + ", ".join(missing))

    tokens = load_tokens()
    granted_scopes = set(tokens.get("granted_scopes", [])) if tokens else set()
    has_required_scopes = set(REQUIRED_SCOPES).issubset(granted_scopes)
    if (
        tokens
        and has_required_scopes
        and tokens.get("expires_at", 0) > time.time() + 30
    ):
        return tokens

    if tokens and has_required_scopes and tokens.get("refresh_token"):
        try:
            return refresh_access_token(tokens["refresh_token"])
        except requests.HTTPError:
            pass

    redirect_uri = os.environ["SPOTIFY_REDIRECT_URI"]
    code, code_verifier = get_authorization_code(redirect_uri)
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": os.environ["SPOTIFY_CLIENT_ID"],
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    response.raise_for_status()
    tokens = response.json()
    save_tokens(tokens)
    return tokens
