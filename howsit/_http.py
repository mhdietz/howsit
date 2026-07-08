"""Shared HTTP fetch helper for every howsit fetcher."""

import urllib.request

USER_AGENT = "howsit/0.1 (public-data ocean data library)"
HTTP_TIMEOUT = 20


def http_get(url: str, timeout: int = HTTP_TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")
