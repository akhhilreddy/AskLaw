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

## Temporary Render proxy measurement (required before enabling IP limits)

New settings: `TRUSTED_PROXY_HOPS=0` and `PROXY_DIAGNOSTICS=false` by default.
The startup script disables Uvicorn's blanket forwarded-header trust. With zero
hops, the socket peer is used and headers are ignored (appropriate locally).
With N hops, the Nth address **from the right** is used. Missing, malformed, or
too-short chains fall back to the socket peer. Fixed-hop trust is appropriate
only when every public request must traverse the same controlled proxy chain;
it cannot authenticate a proxy on a directly internet-accessible backend port.
Do not use Render's outbound IP ranges as an inbound proxy allowlist.

After explicitly deploying this branch for the check:

1. In Render, set `PROXY_DIAGNOSTICS=true`, keeping `TRUSTED_PROXY_HOPS=0`.
2. From your Mac, run these commands (no API token is needed):

```sh
asklaw_public_ip=$(curl --fail --silent --show-error https://api.ipify.org)
curl --fail --silent --show-error https://asklaw-api.onrender.com/health \
  -H "X-AskLaw-Debug-Client-IP: $asklaw_public_ip"
curl --fail --silent --show-error https://asklaw-api.onrender.com/health \
  -H "X-AskLaw-Debug-Client-IP: $asklaw_public_ip" \
  -H "X-Forwarded-For: 203.0.113.123"
unset asklaw_public_ip
```

3. Inspect Render's `proxy_probe` logs. They contain only `entries`,
   `expected_from_right`, and `configured_hops`, never addresses or headers.
   `expected_from_right` must be a positive integer and **the same in both
   requests**, even when a forged leftmost address is supplied. Repeat from
   another device/network. If it is missing or changes, do not enable hops;
   investigate the proxy chain first. A VPN/IPv6 mismatch can invalidate the
   comparison. Do not guess N from the total entry count.
4. Set `TRUSTED_PROXY_HOPS` to the measured N. Set `PROXY_DIAGNOSTICS=false`.
   Redeploy and repeat the check briefly if necessary. Share only the redacted
   log lines so the temporary diagnostic code can then be removed in a follow-up
   commit. Production-chain verification cannot be completed from local tests.

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
