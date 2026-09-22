"""The credential must never reach the agent through an error message.

Regression test for a real leak: `requests` puts the full request URL in its
HTTPError message, and the API key used to travel in that URL as `token=`.
The key now travels in a header, and Signal.failed redacts as a backstop.
"""

import os
import unittest
from unittest.mock import patch

import requests

from equity_intel_mcp.signal import Signal

KEY = "SUPERSECRET_TOKEN_ABC123"


class RedactionTest(unittest.TestCase):
    def _leaky_error(self):
        url = "https://finnhub.io/api/v1/quote?symbol=AAPL&token=" + KEY
        return requests.exceptions.HTTPError(
            "401 Client Error: Unauthorized for url: " + url
        )

    def test_key_absent_from_error_and_summary(self):
        with patch.dict(os.environ, {"FINNHUB_API_KEY": KEY}):
            r = Signal.failed("quote", str(self._leaky_error()))
        self.assertNotIn(KEY, r.error)
        self.assertNotIn(KEY, r.summary)
        self.assertIn("REDACTED", r.error)

    def test_query_string_redacted_even_without_env(self):
        """A key we never set must still be stripped: the pattern is enough."""
        with patch.dict(os.environ, {}, clear=True):
            r = Signal.failed("quote", "failed for url: https://x/y?token=OTRA_CLAVE_9999")
        self.assertNotIn("OTRA_CLAVE_9999", r.error)

    def test_prefix_is_kept_so_the_message_stays_readable(self):
        with patch.dict(os.environ, {}, clear=True):
            r = Signal.failed("quote", "https://x/y?token=OTRA_CLAVE_9999")
        self.assertIn("token=", r.error)

    def test_key_with_trailing_newline_is_still_hidden(self):
        """A key pasted with a trailing newline is rejected by urllib3, which
        echoes the value back. That must not surface the credential."""
        dirty = KEY + chr(10)
        with patch.dict(os.environ, {"FINNHUB_API_KEY": dirty}):
            msg = (
                "Invalid leading whitespace, reserved character(s), or return "
                "character(s) in header value: " + repr(dirty)
            )
            r = Signal.failed("quote", msg)
        self.assertNotIn(KEY, r.error)
        self.assertNotIn(KEY, r.summary)

    def test_ordinary_message_survives_untouched(self):
        r = Signal.failed("quote", "no price data for ZZZZ")
        self.assertIn("no price data for ZZZZ", r.error)


if __name__ == "__main__":
    unittest.main()
