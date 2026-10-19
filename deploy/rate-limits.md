# Shared usage limits and Render proxy check

The limiter reuses `CELERY_BROKER_URL`, including verified TLS for `rediss://`.
No Redis credentials or application API URLs change. Redis errors fail open,
with a sanitized warning. Connection and socket waits are one second each,
with no automatic Redis retries. All limit keys expire automatically.

| Request | Policy |
| --- | --- |
| Password login (including `/auth/token`) | 5/5 minutes per email; 20/minute per IP |
| Signup | 3/hour per email; 10/hour per IP |
| Guest entry | 10/hour per IP |
| Chat | 10/minute and 100/24 hours per user; 2 concurrent requests |
| Upload | 5/hour per user; 1 concurrent request |

Windows start with the first admitted request, not at midnight. Each accepted
chat request counts, including a stopped/failed generation. Concurrency leases
expire after 15 minutes if the process dies, and are released at request end.
The existing frontend displays the backend's 429 detail, including wait time.

## Verified Render proxy configuration

On October 14, 2026, the current Render service was measured with a normal
request and a request containing a forged leftmost `X-Forwarded-For` value.
The chains contained three and four addresses respectively; the real client
remained **third from the right** in both. The measured configuration is:

```text
TRUSTED_PROXY_HOPS=3
```

This is the measured value for the current deployment, not a universal Render
guarantee. Revalidate the proxy chain if the hosting/network topology changes.
The application retains `TRUSTED_PROXY_HOPS=0` as its safe local default.
The startup script disables Uvicorn's blanket forwarded-header trust. With zero
hops, the socket peer is used and headers are ignored (appropriate locally).
With N hops, the Nth address **from the right** is used. Missing, malformed, or
too-short chains fall back to the socket peer. Fixed-hop trust is appropriate
only when every public request must traverse the same controlled proxy chain;
it cannot authenticate a proxy on a directly internet-accessible backend port.
Do not use Render's outbound IP ranges as an inbound proxy allowlist.

### HTTPS redirect fix

With hops left at zero behind Render's TLS-terminating proxy, the API saw HTTP
and redirected `/conversations` to `http://.../conversations/`. Browsers blocked
that HTTPS-to-HTTP redirect, causing conversation requests to show a network
error. With the measured hop count of three, the middleware restores the HTTPS
scheme from the forwarded protocol. The live redirect was verified as:

```text
location: https://asklaw-api.onrender.com/conversations/
```

The temporary measurement code and its setting have been removed. This
documentation records the existing deployment values; it does not change them.

## Redis command cost

Every admitted request uses **one EVAL**. Chat/upload use **one ZREM** at request
completion as well. No EVALSHA registration or application PING is needed.
Lua checks each quota with GET, increments it with INCR, and sets EXPIRE only
when the counter is first created. Concurrency adds TIME, ZREMRANGEBYSCORE,
ZCARD, ZADD, and EXPIRE (five internal commands).

| Request | Client calls | Lua internals, existing windows / new windows | Total including EVAL/release |
| --- | --- | --- | --- |
| Login/signup | 1 | 4 / 6 | 5 / 7 |
| Guest | 1 | 2 / 3 | 3 / 4 |
| Chat | 2 | 9 / 11 | 11 / 13 |
| Upload | 2 | 7 / 8 | 9 / 10 |

Mixed new/existing windows fall between these totals. A quota-denied request
uses GET up to the rejecting bucket plus one TTL (and EVAL). A concurrency
denial additionally uses TIME, ZREMRANGEBYSCORE, ZCARD, ZRANGE, but no increments
or release. Counts exclude connection setup (AUTH/SELECT/CLIENT commands).
These are command executions, not a guarantee of how Upstash bills Lua scripts.
