#!/usr/bin/env python3

import json
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


class PiHealthConnection:
    def __init__(self, host, port, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _get_json(self, path, params=None):
        query = ""
        if params:
            query = "?" + urlencode(params)
        url = f"http://{self.host}:{self.port}{path}{query}"
        try:
            with urlopen(url, timeout=self.timeout) as response:
                return json.load(response)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
            RemoteDisconnected,
            OSError,
        ) as exc:
            raise RuntimeError(f"failed to query Pi health server at {url}: {exc}") from exc

    def get_health(self):
        return self._get_json("/health")

    def get_events(self, limit=20):
        return self._get_json("/events", {"limit": int(limit)})
