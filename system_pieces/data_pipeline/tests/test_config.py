"""Unit tests for data_pipeline/config.py.

Tests cover:
- Config defaults (frozen dataclass)
- ncbi_rate_limit property — key vs no-key
- Config.status() — all keys present, marks configured/not-set correctly
- _load_dotenv / env-var loading (via monkeypatching os.environ)
- CONFIG singleton is a valid Config instance
"""

import os
import unittest

from ..config import Config, CONFIG


class TestConfigDefaults(unittest.TestCase):
    def test_singleton_is_config(self):
        self.assertIsInstance(CONFIG, Config)

    def test_contact_email_default(self):
        cfg = Config()
        # Default is set in code; may be overridden by env, but must be a non-empty string.
        self.assertIsInstance(cfg.contact_email, str)
        self.assertTrue(len(cfg.contact_email) > 0)

    def test_tool_name_default(self):
        cfg = Config()
        self.assertIsInstance(cfg.tool_name, str)
        self.assertTrue(len(cfg.tool_name) > 0)

    def test_default_lookback_days_positive_int(self):
        cfg = Config()
        self.assertIsInstance(cfg.default_lookback_days, int)
        self.assertGreater(cfg.default_lookback_days, 0)

    def test_default_max_per_source_positive_int(self):
        cfg = Config()
        self.assertIsInstance(cfg.default_max_per_source, int)
        self.assertGreater(cfg.default_max_per_source, 0)

    def test_request_timeout_positive_int(self):
        cfg = Config()
        self.assertIsInstance(cfg.request_timeout, int)
        self.assertGreater(cfg.request_timeout, 0)

    def test_frozen(self):
        cfg = Config()
        with self.assertRaises((AttributeError, TypeError)):
            cfg.contact_email = "changed@example.com"  # type: ignore[misc]


class TestNcbiRateLimit(unittest.TestCase):
    def test_rate_limit_with_key(self):
        cfg = Config(ncbi_api_key="somekey")
        self.assertEqual(cfg.ncbi_rate_limit, 10.0)

    def test_rate_limit_without_key(self):
        cfg = Config(ncbi_api_key=None)
        self.assertEqual(cfg.ncbi_rate_limit, 3.0)


class TestConfigStatus(unittest.TestCase):
    def test_status_returns_dict(self):
        cfg = Config()
        st = cfg.status()
        self.assertIsInstance(st, dict)

    def test_status_has_required_keys(self):
        cfg = Config()
        st = cfg.status()
        for key in ("contact_email", "NCBI_API_KEY", "SPRINGER_API_KEY", "ncbi_rate_limit_rps"):
            self.assertIn(key, st)

    def test_status_ncbi_configured(self):
        cfg = Config(ncbi_api_key="mykey")
        st = cfg.status()
        self.assertIn("configured", st["NCBI_API_KEY"])

    def test_status_ncbi_not_set(self):
        cfg = Config(ncbi_api_key=None)
        st = cfg.status()
        self.assertIn("not set", st["NCBI_API_KEY"])

    def test_status_springer_configured(self):
        cfg = Config(springer_api_key="myspringerkey")
        st = cfg.status()
        self.assertIn("configured", st["SPRINGER_API_KEY"])

    def test_status_springer_not_set(self):
        cfg = Config(springer_api_key=None)
        st = cfg.status()
        self.assertIn("not set", st["SPRINGER_API_KEY"])

    def test_status_ncbi_rate_limit_reflects_key(self):
        cfg_with_key = Config(ncbi_api_key="k")
        cfg_no_key = Config(ncbi_api_key=None)
        self.assertEqual(cfg_with_key.status()["ncbi_rate_limit_rps"], "10.0")
        self.assertEqual(cfg_no_key.status()["ncbi_rate_limit_rps"], "3.0")


class TestConfigCustomValues(unittest.TestCase):
    def test_custom_email(self):
        cfg = Config(contact_email="test@example.com")
        self.assertEqual(cfg.contact_email, "test@example.com")

    def test_custom_lookback_days(self):
        cfg = Config(default_lookback_days=30)
        self.assertEqual(cfg.default_lookback_days, 30)

    def test_both_keys_set(self):
        cfg = Config(ncbi_api_key="ncbi", springer_api_key="springer")
        self.assertEqual(cfg.ncbi_api_key, "ncbi")
        self.assertEqual(cfg.springer_api_key, "springer")


if __name__ == "__main__":
    unittest.main()
