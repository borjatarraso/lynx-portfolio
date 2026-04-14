"""
Tests for input validation module.
"""

import pytest

from lynx_portfolio.validation import (
    validate_ticker,
    validate_isin,
    validate_exchange,
    validate_shares,
    validate_price,
    sanitise_search_query,
)


# ---------------------------------------------------------------------------
# Ticker validation
# ---------------------------------------------------------------------------

class TestValidateTicker:
    def test_valid_simple(self):
        assert validate_ticker("AAPL") == ("AAPL", None)

    def test_valid_with_suffix(self):
        assert validate_ticker("NESN.SW") == ("NESN.SW", None)

    def test_valid_with_hyphen(self):
        assert validate_ticker("BRK-B") == ("BRK-B", None)

    def test_valid_with_caret(self):
        assert validate_ticker("^GSPC") == ("^GSPC", None)

    def test_uppercased(self):
        assert validate_ticker("aapl") == ("AAPL", None)

    def test_trimmed(self):
        assert validate_ticker("  AAPL  ") == ("AAPL", None)

    def test_empty(self):
        _, err = validate_ticker("")
        assert err is not None

    def test_none_string(self):
        _, err = validate_ticker("   ")
        assert err is not None

    def test_too_long(self):
        _, err = validate_ticker("A" * 25)
        assert err is not None

    def test_spaces(self):
        _, err = validate_ticker("A B C")
        assert err is not None

    def test_sql_injection(self):
        _, err = validate_ticker("'; DROP TABLE--")
        assert err is not None

    def test_unicode(self):
        _, err = validate_ticker("\u65e5\u672c\u8a9e")
        assert err is not None

    def test_semicolon(self):
        _, err = validate_ticker("AAPL;GOOG")
        assert err is not None

    def test_backslash(self):
        _, err = validate_ticker("AAPL\\n")
        assert err is not None


# ---------------------------------------------------------------------------
# ISIN validation
# ---------------------------------------------------------------------------

class TestValidateISIN:
    def test_valid(self):
        assert validate_isin("US0378331005") == ("US0378331005", None)

    def test_valid_lowercase(self):
        assert validate_isin("ch0038863350") == ("CH0038863350", None)

    def test_too_short(self):
        _, err = validate_isin("US037")
        assert err is not None

    def test_too_long(self):
        _, err = validate_isin("US03783310050")
        assert err is not None

    def test_no_leading_letters(self):
        _, err = validate_isin("123456789012")
        assert err is not None

    def test_special_chars(self):
        _, err = validate_isin("US0378331;05")
        assert err is not None

    def test_empty(self):
        _, err = validate_isin("")
        assert err is not None


# ---------------------------------------------------------------------------
# Exchange validation
# ---------------------------------------------------------------------------

class TestValidateExchange:
    def test_valid(self):
        assert validate_exchange("SW") == ("SW", None)

    def test_valid_lowercase(self):
        assert validate_exchange("de") == ("DE", None)

    def test_too_long(self):
        _, err = validate_exchange("ABCDEFGHIJ")
        assert err is not None

    def test_special(self):
        _, err = validate_exchange("S;W")
        assert err is not None

    def test_empty(self):
        _, err = validate_exchange("")
        assert err is not None


# ---------------------------------------------------------------------------
# Shares validation
# ---------------------------------------------------------------------------

class TestValidateShares:
    def test_valid_integer(self):
        assert validate_shares(10) == (10.0, None)

    def test_valid_float(self):
        assert validate_shares(0.5) == (0.5, None)

    def test_valid_string(self):
        assert validate_shares("25") == (25.0, None)

    def test_zero(self):
        _, err = validate_shares(0)
        assert err is not None

    def test_negative(self):
        _, err = validate_shares(-5)
        assert err is not None

    def test_too_large(self):
        _, err = validate_shares(2_000_000_000)
        assert err is not None

    def test_non_numeric(self):
        _, err = validate_shares("abc")
        assert err is not None

    def test_none(self):
        _, err = validate_shares(None)
        assert err is not None

    def test_empty_string(self):
        _, err = validate_shares("")
        assert err is not None


# ---------------------------------------------------------------------------
# Price validation
# ---------------------------------------------------------------------------

class TestValidatePrice:
    def test_valid(self):
        assert validate_price(150.0) == (150.0, None)

    def test_zero_valid(self):
        assert validate_price(0) == (0.0, None)

    def test_none_means_not_provided(self):
        assert validate_price(None) == (None, None)

    def test_empty_string_means_not_provided(self):
        assert validate_price("") == (None, None)

    def test_negative(self):
        _, err = validate_price(-10)
        assert err is not None

    def test_too_large(self):
        _, err = validate_price(2_000_000_000)
        assert err is not None

    def test_non_numeric(self):
        _, err = validate_price("abc")
        assert err is not None

    def test_string_number(self):
        assert validate_price("99.50") == (99.5, None)


# ---------------------------------------------------------------------------
# Search query sanitisation
# ---------------------------------------------------------------------------

class TestSanitiseSearchQuery:
    def test_valid(self):
        assert sanitise_search_query("Apple Inc") == ("Apple Inc", None)

    def test_trimmed(self):
        assert sanitise_search_query("  Apple  ") == ("Apple", None)

    def test_empty(self):
        _, err = sanitise_search_query("")
        assert err is not None

    def test_blank(self):
        _, err = sanitise_search_query("   ")
        assert err is not None

    def test_too_long(self):
        _, err = sanitise_search_query("A" * 150)
        assert err is not None

    def test_control_chars_stripped(self):
        result, err = sanitise_search_query("Apple\x00Inc")
        assert err is None
        assert result == "AppleInc"

    def test_unicode_allowed(self):
        result, err = sanitise_search_query("Nestl\u00e9")
        assert err is None
        assert result == "Nestl\u00e9"
