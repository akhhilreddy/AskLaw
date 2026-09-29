"""Confirm that the private MCP HTTP endpoint is accepting requests."""

from urllib.error import HTTPError
from urllib.request import Request, urlopen


request = Request(
    "http://127.0.0.1:8001/mcp",
    headers={"Accept": "application/json, text/event-stream"},
)

try:
    with urlopen(request, timeout=5) as response:
        status = response.status
except HTTPError as exc:
    status = exc.code

if status >= 500:
    raise RuntimeError(f"MCP endpoint returned HTTP {status}")
