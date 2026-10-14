"""Fixed-hop proxy handling; only enable hops on a proxy-only deployment."""
import ipaddress
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def forwarded_addresses(value):
    if not value or len(value) > 2048:
        return []
    try:
        addresses = [str(ipaddress.ip_address(part.strip())) for part in value.split(",")]
        return addresses if len(addresses) <= 20 else []
    except ValueError:
        return []


class ProxyHopMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        addresses = forwarded_addresses(headers.get(b"x-forwarded-for", b"").decode("latin1"))
        hops = settings.TRUSTED_PROXY_HOPS
        if settings.PROXY_DIAGNOSTICS and scope.get("path") == "/health":
            expected = forwarded_addresses(headers.get(b"x-asklaw-debug-client-ip", b"").decode("latin1"))
            position = next((i for i, address in enumerate(reversed(addresses), 1)
                             if expected and address == expected[0]), None)
            # Temporary opt-in diagnostic: no addresses, credentials or full headers.
            logger.warning("proxy_probe entries=%s expected_from_right=%s configured_hops=%s", len(addresses), position, hops)
        if hops and len(addresses) >= hops:
            scope = dict(scope)
            scope["client"] = (addresses[-hops], 0)
            protocol = headers.get(b"x-forwarded-proto", b"").decode("latin1").split(",")[-1].strip()
            if protocol in {"https", "http"}:
                scope["scheme"] = protocol
        return await self.app(scope, receive, send)
