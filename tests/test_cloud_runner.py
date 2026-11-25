import unittest
import cloud_runner
import worker


class CloudRunnerTests(unittest.TestCase):
    def test_build_config_accepts_only_official_https_host(self):
        cfg = cloud_runner.build_config(
            "https://sus10beats.great-site.net",
            "a" * 64,
        )
        self.assertEqual(cfg["site_url"], "https://sus10beats.great-site.net")
        self.assertEqual(cfg["worker_name"], "sus10-github-actions-cloud")

    def test_build_config_rejects_wrong_host_and_paths(self):
        for bad in (
            "http://sus10beats.great-site.net",
            "https://example.com",
            "https://sus10beats.great-site.net/admin",
            "https://sus10beats.great-site.net?x=1",
        ):
            with self.subTest(site=bad), self.assertRaises(worker.WorkerError):
                cloud_runner.build_config(bad, "b" * 64)

    def test_build_config_requires_long_secret(self):
        with self.assertRaises(worker.WorkerError):
            cloud_runner.build_config("https://sus10beats.great-site.net", "short")

    def test_signature_is_hmac_sha256_and_includes_exact_bridge_path(self):
        secret = "c" * 64
        headers = worker.canonical_signature(
            secret,
            "POST",
            "/bridge/youtube/v1/heartbeat",
            "0" * 64,
            timestamp="1795530000",
        )
        self.assertRegex(headers["X-Sus10-Worker-Signature"], r"^[0-9a-f]{64}$")
        self.assertEqual(headers["X-Sus10-Worker-Timestamp"], "1795530000")


if __name__ == "__main__":
    unittest.main(verbosity=2)
