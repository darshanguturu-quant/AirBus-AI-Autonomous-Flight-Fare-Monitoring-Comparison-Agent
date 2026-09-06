"""
Strict Source Allowlist & Verification Engine.
Enforces Sections 5 & 6 of specifications:
- ONLY retrieves flight data from websites whose primary purpose is flight search, airline booking, or airfare comparison.
- Strictly blocks and rejects social media, forums, blogs, news websites, and unverified snippets.
- Implements Source Reliability Hierarchy: Official Airline > Verified Flight Search > Travel OTA.
"""
import urllib.parse
from typing import Tuple, Optional, Dict
from config import APPROVED_SOURCES, STRICTLY_DISALLOWED_PATTERNS


class SourceSecurityException(Exception):
    """Raised when an unauthorized or unapproved data source is encountered."""
    pass


def extract_domain(url_or_domain: str) -> str:
    """Cleanly extracts domain name from URL or raw string."""
    if not url_or_domain:
        return ""
    text = url_or_domain.strip().lower()
    if not text.startswith("http://") and not text.startswith("https://"):
        text = "https://" + text
    try:
        parsed = urllib.parse.urlparse(text)
        netloc = parsed.netloc
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        # remove 'www.' prefix if present
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def is_strictly_disallowed(url_or_domain: str) -> bool:
    """Checks if source matches any forbidden domain patterns (social media, blogs, forums)."""
    text = url_or_domain.lower()
    for pattern in STRICTLY_DISALLOWED_PATTERNS:
        if pattern in text:
            return True
    return False


def validate_and_classify_source(url_or_domain: str) -> Tuple[bool, Optional[Dict]]:
    """
    Validates if a source domain is on the approved allowlist.
    Returns:
        (is_approved: bool, metadata: Optional[Dict])
    """
    if is_strictly_disallowed(url_or_domain):
        return False, None

    domain = extract_domain(url_or_domain)
    if not domain:
        return False, None

    # Check direct match
    if domain in APPROVED_SOURCES:
        return True, APPROVED_SOURCES[domain]

    # Check subdomain match (e.g. flights.google.com -> google.com)
    for approved_dom, meta in APPROVED_SOURCES.items():
        if domain == approved_dom or domain.endswith("." + approved_dom):
            return True, meta

    return False, None


def get_source_reliability(domain: str) -> Tuple[str, int]:
    """
    Returns (source_type, reliability_score) based on approved hierarchy:
    Official Airline (100) > Verified Flight Search (80) > Travel OTA (60) > Unverified (0)
    """
    is_valid, meta = validate_and_classify_source(domain)
    if is_valid and meta:
        return meta["type"], meta["reliability"]
    return "Unverified", 0
