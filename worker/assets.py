"""Download job media only from explicitly trusted HTTPS hosts."""
from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
from urllib.parse import urlparse

import requests


def validate_asset_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Media asset URL must use HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("Media asset URL must not contain credentials.")
    host = parsed.hostname.lower()
    if host not in allowed_hosts:
        raise ValueError("Media asset host is not on the worker allow-list.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as exc:
            raise ValueError("Media asset host could not be resolved.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Private or local network asset hosts are not allowed.")


def download_asset(url: str, allowed_hosts: frozenset[str], max_bytes: int, suffix: str) -> str:
    validate_asset_url(url, allowed_hosts)
    response = requests.get(url, stream=True, timeout=(15, 60), allow_redirects=False)
    response.raise_for_status()
    length = response.headers.get("Content-Length")
    if length and int(length) > max_bytes:
        response.close()
        raise ValueError("Media asset exceeds the configured size limit.")

    fd, path = tempfile.mkstemp(prefix="sus10-worker-", suffix=suffix)
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Media asset exceeds the configured size limit.")
                output.write(chunk)
        if total == 0:
            raise ValueError("Media asset download was empty.")
        return path
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        response.close()
