"""Client for Dash0's public API, using environment or an ignored local config."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


class Dash0:
    def __init__(self, credentials=Path(".secrets/dash0.json")):
        self.config = (
            json.loads(credentials.read_text()) if credentials.exists() else {}
        )
        for key, env in [
            ("token", "DASH0_AUTH_TOKEN"),
            ("api_url", "DASH0_API_URL"),
            ("dataset", "DASH0_DATASET"),
        ]:
            if os.environ.get(env):
                self.config[key] = os.environ[env]
        self.config.setdefault("dataset", "default")
        if not self.config.get("token") or not self.config.get("api_url"):
            raise ValueError(
                "Set DASH0_AUTH_TOKEN and DASH0_API_URL, or provide .secrets/dash0.json"
            )
        if not self.config["api_url"].startswith("https://"):
            raise ValueError("Dash0 API URL must use HTTPS")

    def call(self, path, body=None, method=None):
        req = urllib.request.Request(
            self.config["api_url"].rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + self.config["token"],
                "Content-Type": "application/json",
                "Dash0-Dataset": self.config["dataset"],
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as exc:
            # Do not echo a server response that could include request headers.
            raise RuntimeError(
                f"Dash0 HTTP {exc.code} for {path.split('?')[0]}"
            ) from None
