"""Unit tests for worker configuration and signature construction."""
from __future__ import annotations

import hashlib
import hmac
import os
import unittest
from unittest.mock import patch

from worker.client import MarketplaceClient
from worker.config import Settings


class ConfigTests(unittest.TestCase):
    def test_publishing_defaults_to_disabled(self):
        with patch.dict(os.environ, {"SITE_API_BASE_URL": "https://example.test"}, clear=True):
            self.assertFalse(Settings.from_env().publish_enabled)

    def test_http_marketplace_url_is_rejected(self):
        with patch.dict(os.environ, {"SITE_API_BASE_URL": "http://example.test"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_zero_limit_is_rejected(self):
        with patch.dict(os.environ, {"MAX_AUDIO_MB": "0"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


class SigningTests(unittest.TestCase):
    def test_short_secret_is_rejected(self):
        with self.assertRaises(ValueError):
            MarketplaceClient("https://example.test", "short")

    def test_hmac_signature_is_64_hex_characters(self):
        key = b"x" * 40
        body = b'{"worker_id":"runner-1"}'
        digest = hashlib.sha256(body).hexdigest()
        message = f"1770000000\nPOST\n/api/worker/v1/jobs/claim\n{digest}".encode()
        signature = hmac.new(key, message, hashlib.sha256).hexdigest()
        self.assertEqual(len(signature), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in signature))


if __name__ == "__main__":
    unittest.main()
