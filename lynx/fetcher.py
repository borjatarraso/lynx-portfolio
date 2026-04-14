"""
Data fetchers for Lynx Portfolio.

Resolution strategy
-------------------
1. If the user supplies a ticker that already contains a suffix (e.g. NESN.SW,
   VWCE.DE) → use it as-is.
2. Otherwise: call yf.Search(query) which returns Yahoo-native full symbols
   (suffix included). Filter to real/primary exchanges only.
3. ISIN search: try yf.Search(ISIN) first; if it returns nothing, use OpenFIGI
   to get the base ticker, then run yf.Search on that.
4. When multiple exchanges remain after filtering, apply:
   - explicit --exchange flag (user's choice)
   - ISIN country code → preferred exchange heuristic
   - score-ranked first result as final fallback.
"""

import re
from typing import Optional, Dict, List, Tuple

import requests
import yfinance as yf

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_TIMEOUT = 12  # seconds

# ---------------------------------------------------------------------------
# Yahoo Finance internal exchange code → (ticker_suffix, display_name, currency)
# ---------------------------------------------------------------------------
YAHOO_EXCHANGE_INFO: Dict[str, Tuple[str, str, str]] = {
    # United States
    "NMS":  ("",    "NASDAQ",                          "USD"),
    "NYQ":  ("",    "NYSE",                            "USD"),
    "NGM":  ("",    "NASDAQ Global Market",            "USD"),
    "ASE":  ("",    "NYSE American",                   "USD"),
    "PCX":  ("",    "NYSE Arca",                       "USD"),
    "NCM":  ("",    "NASDAQ Capital Market",           "USD"),
    "BTS":  ("",    "BATS Exchange",                   "USD"),
    # US OTC markets  (Yahoo Finance uses several codes depending on tier)
    "PNK":  ("",    "OTC Pink Sheets",                 "USD"),
    "OBB":  ("",    "OTC Bulletin Board",              "USD"),   # legacy alias
    "OQB":  ("",    "OTC Quoted Board",                "USD"),   # actual code Yahoo returns
    "OTC":  ("",    "OTC Markets",                     "USD"),   # generic OTC
    "GREY": ("",    "OTC Grey Market",                 "USD"),
    # Europe
    "EBS":  (".SW", "SIX Swiss Exchange",              "CHF"),
    "ZRH":  (".SW", "SIX Swiss Exchange",              "CHF"),
    "GER":  (".DE", "Deutsche Börse XETRA",            "EUR"),
    "FRA":  (".F",  "Frankfurt Stock Exchange",        "EUR"),
    "STU":  (".SG", "Stuttgart Stock Exchange",        "EUR"),
    "MUN":  (".MU", "Munich Stock Exchange",           "EUR"),
    "DUS":  (".DU", "Düsseldorf Stock Exchange",       "EUR"),
    "BER":  (".BE", "Berlin Stock Exchange",           "EUR"),
    "HAM":  (".HH", "Hamburg Stock Exchange",          "EUR"),
    "HAN":  (".HA", "Hannover Stock Exchange",         "EUR"),
    "PAR":  (".PA", "Euronext Paris",                  "EUR"),
    "AMS":  (".AS", "Euronext Amsterdam",              "EUR"),
    "MIL":  (".MI", "Borsa Italiana",                  "EUR"),
    "MCE":  (".MC", "Madrid Stock Exchange",           "EUR"),
    "LSE":  (".L",  "London Stock Exchange",           "GBP"),
    "IOB":  (".IL", "LSE International Order Book",   "USD"),
    "OSL":  (".OL", "Oslo Stock Exchange",             "NOK"),
    "STO":  (".ST", "Nasdaq OMX Stockholm",            "SEK"),
    "CPH":  (".CO", "Nasdaq OMX Copenhagen",           "DKK"),
    "HEL":  (".HE", "Nasdaq OMX Helsinki",             "EUR"),
    "VIE":  (".VI", "Vienna Stock Exchange",           "EUR"),
    "BRU":  (".BR", "Euronext Brussels",               "EUR"),
    "WAR":  (".WA", "Warsaw Stock Exchange",           "PLN"),
    "LIS":  (".LS", "Euronext Lisbon",                 "EUR"),
    "ATH":  (".AT", "Athens Stock Exchange",           "EUR"),
    "DUB":  (".IR", "Euronext Dublin",                 "EUR"),
    "BUD":  (".BD", "Budapest Stock Exchange",         "HUF"),
    "ICE":  (".IC", "Nasdaq OMX Iceland",              "ISK"),
    # Americas
    "MEX":  (".MX", "Bolsa Mexicana de Valores",       "MXN"),
    "SAO":  (".SA", "B3 (Brazil)",                     "BRL"),
    "SGO":  (".SN", "Bolsa de Santiago",               "CLP"),
    "BUE":  (".BA", "Bolsa de Buenos Aires",           "ARS"),
    # Canada — Yahoo Finance returns "TOR" for TSX and "VAN" for TSXV.
    # Legacy codes "TSX" / "CVE" are kept as aliases in case Yahoo returns them.
    "TOR":  (".TO", "Toronto Stock Exchange",          "CAD"),   # actual Yahoo code
    "TSX":  (".TO", "Toronto Stock Exchange",          "CAD"),   # legacy alias
    "VAN":  (".V",  "TSX Venture Exchange",            "CAD"),   # actual Yahoo code (CDNX)
    "CVE":  (".V",  "TSX Venture Exchange",            "CAD"),   # legacy alias
    "NEO":  (".NE", "NEO Exchange",                    "CAD"),
    "CNQ":  (".CN", "Canadian Securities Exchange",    "CAD"),
    # Asia-Pacific
    "ASX":  (".AX", "Australian Securities Exchange",  "AUD"),
    "NZX":  (".NZ", "New Zealand Stock Exchange",      "NZD"),
    "HKG":  (".HK", "Hong Kong Stock Exchange",        "HKD"),
    "TYO":  (".T",  "Tokyo Stock Exchange",            "JPY"),
    "SES":  (".SI", "Singapore Exchange",              "SGD"),
    "KSE":  (".KS", "Korea Stock Exchange",            "KRW"),
    "TAI":  (".TW", "Taiwan Stock Exchange",           "TWD"),
    "BSE":  (".BO", "BSE India",                       "INR"),
    "NSE":  (".NS", "NSE India",                       "INR"),
    "SHH":  (".SS", "Shanghai Stock Exchange",         "CNY"),
    "SHZ":  (".SZ", "Shenzhen Stock Exchange",         "CNY"),
    "SET":  (".BK", "Stock Exchange of Thailand",      "THB"),
    "KLS":  (".KL", "Bursa Malaysia",                  "MYR"),
    "JKT":  (".JK", "Indonesia Stock Exchange",        "IDR"),
    # Africa
    "JSE":  (".JO", "Johannesburg Stock Exchange",     "ZAR"),
}

# ---------------------------------------------------------------------------
# Exchange codes treated as primary/real exchanges (not dark pools / MTFs)
# ---------------------------------------------------------------------------
PRIMARY_EXCHANGE_CODES: frozenset = frozenset(YAHOO_EXCHANGE_INFO.keys())

# ---------------------------------------------------------------------------
# ISIN 2-letter country code → preferred Yahoo exchange code
# Used for auto-selection when multiple exchanges are available.
# ---------------------------------------------------------------------------
ISIN_COUNTRY_TO_EXCHANGE_CODE = {
    "US": "",      # any US exchange (no suffix)
    "CA": "TOR",   # Toronto Stock Exchange (Yahoo code); TSXV ("VAN") tried as fallback
    "GB": "LSE",
    "CH": "EBS",   # SIX Swiss
    "DE": "GER",   # XETRA
    "FR": "PAR",
    "NL": "AMS",
    "IT": "MIL",
    "ES": "MCE",
    "NO": "OSL",
    "SE": "STO",
    "DK": "CPH",
    "FI": "HEL",
    "AT": "VIE",
    "BE": "BRU",
    "PL": "WAR",
    "PT": "LIS",
    "GR": "ATH",
    "IE": "DUB",
    "LU": "PAR",   # Luxembourg-domiciled funds often primary on Euronext Paris
    "AU": "ASX",
    "NZ": "NZX",
    "HK": "HKG",
    "JP": "TYO",
    "SG": "SES",
    "IN": "BSE",
    "ZA": "JSE",
}

# ---------------------------------------------------------------------------
# User-visible suffix → exchange info  (for --exchange flag values)
# ---------------------------------------------------------------------------
SUFFIX_INFO: Dict[str, Tuple[str, str, str]] = {
    suffix.lstrip("."): (exch_code, display, ccy)
    for exch_code, (suffix, display, ccy) in YAHOO_EXCHANGE_INFO.items()
    if suffix  # skip US (empty suffix)
}
# Add US explicitly
SUFFIX_INFO[""] = ("NMS", "US Markets", "USD")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_SENTENCE_LEN = 300

def _first_sentence(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"\.\s+", text, maxsplit=1)
    sentence = parts[0].strip()
    if not sentence:
        return ""
    sentence = sentence if sentence.endswith(".") else sentence + "."
    if len(sentence) > _MAX_SENTENCE_LEN:
        sentence = sentence[:_MAX_SENTENCE_LEN - 3] + "..."
    return sentence


def ticker_has_suffix(ticker: str) -> bool:
    """Return True if ticker already contains an exchange suffix (e.g. NESN.SW)."""
    parts = ticker.rsplit(".", 1)
    return len(parts) == 2 and 1 <= len(parts[1]) <= 3


def extract_suffix(symbol: str) -> str:
    """Return suffix part (after last '.'), or '' for US tickers."""
    parts = symbol.rsplit(".", 1)
    return parts[1] if len(parts) == 2 else ""


# ---------------------------------------------------------------------------
# yf.Search → market list
# ---------------------------------------------------------------------------

def search_markets(
    query: str,
    quote_types: Tuple[str, ...] = ("EQUITY", "ETF", "MUTUALFUND"),
) -> List[Dict]:
    """
    Search Yahoo Finance for 'query' and return a list of primary-market dicts:
        symbol, exchange_code, exchange_display, suffix, quote_type,
        longname, shortname, sector, industry
    Results are filtered to real exchanges (no dark pools) and sorted by
    score descending.
    """
    try:
        results = yf.Search(query, max_results=30).quotes or []
    except Exception:
        return []

    markets = []
    seen_symbols = set()

    for q in results:
        qt = (q.get("quoteType") or "").upper()
        if qt not in quote_types:
            continue
        exch = q.get("exchange", "")
        sym  = q.get("symbol", "")
        if not sym or sym in seen_symbols:
            continue

        suffix    = extract_suffix(sym)

        if exch in PRIMARY_EXCHANGE_CODES:
            exch_info = YAHOO_EXCHANGE_INFO[exch]
            # If the symbol's actual suffix disagrees with what the exchange code
            # implies, trust the suffix — Yahoo sometimes returns an alternate
            # exchange code (e.g. "TOR" for a ".V" TSXV stock).
            expected_suffix = exch_info[0].lstrip(".")
            if suffix != expected_suffix and suffix in SUFFIX_INFO:
                inferred    = SUFFIX_INFO[suffix]
                use_exch    = inferred[0]
                exch_info   = ("." + suffix, inferred[1], inferred[2])
            else:
                use_exch    = exch
        elif suffix and suffix in SUFFIX_INFO:
            # Exchange code unknown to us, but suffix is recognisable — infer.
            inferred    = SUFFIX_INFO[suffix]
            use_exch    = inferred[0]
            exch_info   = ("." + suffix, inferred[1], inferred[2])
        else:
            continue  # Dark pool / MTF / unrecognised exchange — skip.

        seen_symbols.add(sym)
        markets.append({
            "symbol":           sym,
            "exchange_code":    use_exch,
            "exchange_display": exch_info[1],
            "suffix":           suffix,
            "currency":         exch_info[2],
            "quote_type":       qt,
            "longname":         q.get("longname") or q.get("shortname", ""),
            "shortname":        q.get("shortname", ""),
            "sector":           q.get("sector", ""),
            "industry":         q.get("industry", ""),
            "score":            q.get("score", 0),
        })

    # Sort by score descending
    markets.sort(key=lambda x: -x["score"])
    return markets


# ---------------------------------------------------------------------------
# Market auto-picker
# ---------------------------------------------------------------------------

def pick_best_market(
    markets: List[Dict],
    isin: Optional[str] = None,
    preferred_suffix: Optional[str] = None,
) -> Optional[Dict]:
    """
    Pick the best market from a list returned by search_markets().

    Priority:
      1. preferred_suffix (from --exchange flag)
      2. ISIN country code heuristic
      3. Highest score
    """
    if not markets:
        return None

    if preferred_suffix is not None:
        # Normalise (strip leading dot, uppercase)
        norm = preferred_suffix.lstrip(".").upper()
        match = [m for m in markets if m["suffix"].upper() == norm]
        if match:
            return match[0]

    if isin and len(isin) >= 2:
        country = isin[:2].upper()
        pref_exch = ISIN_COUNTRY_TO_EXCHANGE_CODE.get(country)
        if pref_exch is not None:
            if pref_exch == "":
                # US — pick any US exchange (no suffix)
                us_match = [m for m in markets if not m["suffix"]]
                if us_match:
                    return us_match[0]
            else:
                # Build candidate exchange codes: primary preference first, then
                # country-specific alternates (e.g. Canada: TSX then TSXV).
                candidates = [pref_exch]
                if country == "CA":
                    # Canadian ISINs trade on TSX *or* TSXV — try both codes
                    # (real Yahoo codes TOR/VAN and legacy aliases TSX/CVE).
                    candidates += ["TSX", "TOR", "VAN", "CVE", "NEO", "CNQ"]

                for cand in candidates:
                    match = [m for m in markets if m["exchange_code"] == cand]
                    if match:
                        return match[0]

            # Fallback: any listing whose suffix matches the preferred exchange's suffix.
            pref_suffix_tuple = YAHOO_EXCHANGE_INFO.get(pref_exch)
            if pref_suffix_tuple:
                pref_suffix = pref_suffix_tuple[0].lstrip(".")
                match = [m for m in markets if m["suffix"] == pref_suffix]
                if match:
                    return match[0]

    return markets[0]


# ---------------------------------------------------------------------------
# OpenFIGI fallback
# ---------------------------------------------------------------------------

ISIN_COUNTRY_TO_FIGI_PREF: Dict[str, Tuple[str, ...]] = {
    "US": ("US", "UW", "UN"),
    "CH": ("SW",),
    "DE": ("GY",),
    "GB": ("LN",),
    "FR": ("FP",),
    "NL": ("NA",),
    "IT": ("IM",),
    "ES": ("SM",),
}

_FIGI_PREF_DEFAULT = ("US", "UW", "UN", "SW", "GY")


def _isin_to_ticker_openfigi(isin: str) -> Optional[str]:
    """Use OpenFIGI to map ISIN → ticker as a fallback."""
    try:
        resp = requests.post(
            OPENFIGI_URL,
            json=[{"idType": "ID_ISIN", "idValue": isin.upper()}],
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not data[0].get("data"):
            return None
        items = data[0]["data"]
        country = isin[:2].upper() if len(isin) >= 2 else ""
        pref = ISIN_COUNTRY_TO_FIGI_PREF.get(country, _FIGI_PREF_DEFAULT)
        for code in pref:
            for item in items:
                if item.get("exchCode") == code and item.get("ticker"):
                    return item["ticker"]
        for item in items:
            if item.get("ticker"):
                return item["ticker"]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Fetch instrument details from Yahoo Finance
# ---------------------------------------------------------------------------

def fetch_instrument_data(yahoo_symbol: str, isin: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch full instrument info for the given Yahoo Finance symbol.
    Returns a dict or None on failure.
    """
    try:
        stock = yf.Ticker(yahoo_symbol)
        info  = stock.info or {}

        if not info or (not info.get("longName") and not info.get("shortName")
                        and not info.get("regularMarketPrice")):
            return None

        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("navPrice")
            or info.get("previousClose")
        )

        name = info.get("longName") or info.get("shortName") or yahoo_symbol

        qt = info.get("quoteType", "")
        if qt in ("ETF", "MUTUALFUND"):
            sector   = info.get("fundFamily") or info.get("category")
            industry = info.get("category")
        else:
            sector   = info.get("sector")
            industry = info.get("industry")

        description = _first_sentence(info.get("longBusinessSummary") or "") or None

        # Retrieve ISIN from yfinance when the caller didn't supply one.
        resolved_isin = isin
        if not resolved_isin:
            try:
                fetched_isin = stock.isin
                # yfinance returns "-" or empty when ISIN is unavailable.
                if fetched_isin and fetched_isin not in ("-", ""):
                    resolved_isin = fetched_isin
            except Exception:
                pass

        return {
            "name":                  name,
            "current_price":         current_price,
            "regular_market_change": info.get("regularMarketChange"),
            "currency":              info.get("currency"),
            "sector":                sector,
            "industry":              industry,
            "description":           description,
            "isin":                  resolved_isin,
            "exchange_code":         info.get("exchange"),
            "quote_type":            info.get("quoteType", "").upper() or None,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main resolution entry point
# ---------------------------------------------------------------------------

def search_by_name(name: str, max_results: int = 10) -> List[Dict]:
    """Search for instruments by company/fund name.

    Uses Yahoo Finance search which performs fuzzy name matching.
    Returns the same dict format as ``search_markets()``, limited to
    *max_results* entries.
    """
    markets = search_markets(name)
    return markets[:max_results]


def resolve_markets_for_input(
    ticker: Optional[str],
    isin:   Optional[str],
) -> Tuple[List[Dict], Optional[str]]:
    """
    Given raw user input (ticker and/or ISIN), return:
       (markets_list, base_ticker_hint)

    markets_list: output of search_markets() — may be empty
    base_ticker_hint: raw base ticker (without suffix) for display, may be None
    """
    ticker = ticker.upper().strip() if ticker else None
    isin   = isin.upper().strip()   if isin   else None

    # Case 1: ticker already has a suffix → single-element synthetic list
    if ticker and ticker_has_suffix(ticker):
        suffix = extract_suffix(ticker)
        exch   = next(
            (ec for ec, (s, _, __) in YAHOO_EXCHANGE_INFO.items()
             if s == "." + suffix),
            ""
        )
        exch_info = YAHOO_EXCHANGE_INFO.get(exch, ("", suffix, ""))
        return ([{
            "symbol":           ticker,
            "exchange_code":    exch,
            "exchange_display": exch_info[1],
            "suffix":           suffix,
            "currency":         exch_info[2],
            "quote_type":       "",
            "longname":         "",
            "shortname":        "",
            "sector":           "",
            "industry":         "",
            "score":            9999,
        }], ticker.rsplit(".", 1)[0])

    # Case 2: ISIN provided
    if isin:
        isin_markets = search_markets(isin)
        # Extract the base ticker from any ISIN hit (e.g. "IWDA" from "IWDA.L")
        base_from_isin = (
            isin_markets[0]["symbol"].rsplit(".", 1)[0]
            if isin_markets else None
        )
        base_ticker = ticker or base_from_isin

        if not base_ticker:
            # OpenFIGI fallback to resolve ISIN → ticker
            resolved = _isin_to_ticker_openfigi(isin)
            if resolved:
                base_ticker = resolved

        # Now search by the base ticker to discover ALL exchanges
        all_markets: List[Dict] = []
        seen_symbols: set = set()
        if base_ticker:
            all_markets = search_markets(base_ticker)
            seen_symbols = {m["symbol"] for m in all_markets}

        # Merge any ISIN-only hits that weren't in the ticker search
        for m in isin_markets:
            if m["symbol"] not in seen_symbols:
                all_markets.append(m)
                seen_symbols.add(m["symbol"])

        # Re-sort by score
        all_markets.sort(key=lambda x: -x["score"])
        return all_markets, base_ticker

    # Case 3: plain ticker
    if ticker:
        markets = search_markets(ticker)
        if markets:
            return markets, ticker

        # Fallback: the plain ticker matched no equities (common for short
        # tickers that collide with futures or indices, e.g. "NAS" → Oslo).
        # Try appending the most common exchange suffixes and search again.
        _FALLBACK_SUFFIXES = (
            ".OL", ".TO", ".V", ".DE", ".SW", ".PA", ".AS", ".MI",
            ".MC", ".L", ".ST", ".CO", ".HE", ".AX", ".HK", ".T",
        )
        for sfx in _FALLBACK_SUFFIXES:
            fallback = search_markets(ticker + sfx)
            if fallback:
                markets.extend(fallback)
                break  # stop after first hit to keep latency reasonable
        if markets:
            markets.sort(key=lambda x: -x["score"])
        return markets, ticker

    return [], None
