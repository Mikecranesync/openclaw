"""Authentication — API key and Tailscale IP validation."""

from __future__ import annotations


def is_tailscale_ip(ip: str) -> bool:
    """Check if IP is in Tailscale's 100.64.0.0/10 CGNAT range."""
    try:
        octets = ip.split(".")
        return octets[0] == "100" and 64 <= int(octets[1]) <= 127
    except (IndexError, ValueError):
        return False


def validate_api_key(provided: str, expected: str) -> bool:
    """Constant-time API key comparison."""
    import hmac
    return hmac.compare_digest(provided.encode(), expected.encode())
