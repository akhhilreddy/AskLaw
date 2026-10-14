"""Atomic shared fixed-window quotas and expiring per-request leases."""
import hashlib
import logging
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError
from redis.retry import Retry
from redis.backoff import NoBackoff

from app.core.config import settings
from app.core.dependencies import get_current_user

logger = logging.getLogger(__name__)
redis_client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1,
                              socket_timeout=1, retry_on_timeout=False,
                              retry=Retry(NoBackoff(), 0),
                              **({"ssl_cert_reqs": "required"} if settings.CELERY_BROKER_URL.startswith("rediss://") else {}))

# All checks and admissions occur atomically in one EVAL. Denied requests do
# not increment another bucket. TIME uses Redis's clock across API replicas.
ADMIT = """
local n = tonumber(ARGV[1])
for i=1,n do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= tonumber(ARGV[2*i]) then
    return math.max(1,redis.call('TTL', KEYS[i]))
  end
end
local max_active = tonumber(ARGV[2*n+2])
local now = 0
if max_active > 0 then
  local t=redis.call('TIME'); now=tonumber(t[1])
  redis.call('ZREMRANGEBYSCORE',KEYS[n+1],'-inf',now)
  if redis.call('ZCARD',KEYS[n+1]) >= max_active then
    local first=redis.call('ZRANGE',KEYS[n+1],0,0,'WITHSCORES')
    return math.max(1,tonumber(first[2])-now)
  end
end
for i=1,n do
  if redis.call('INCR',KEYS[i]) == 1 then
    redis.call('EXPIRE',KEYS[i],tonumber(ARGV[2*i+1]))
  end
end
if max_active > 0 then
  redis.call('ZADD',KEYS[n+1],now+900,ARGV[2*n+3])
  redis.call('EXPIRE',KEYS[n+1],900)
end
return 0
"""


def bucket(kind, identity):
    # Email addresses and IPs are never stored in clear text or logged.
    digest = hashlib.sha256(str(identity).strip().lower().encode()).hexdigest()
    return f"asklaw:limits:{kind}:{digest}"


def admit(rules, *, active_key=None, concurrency=0):
    token = uuid4().hex
    keys = [key for key, _limit, _window in rules]
    args = [len(rules)]
    for _key, limit, window in rules:
        args.extend([limit, window])
    args.extend([concurrency, token])
    if active_key:
        keys.append(active_key)
    try:
        wait = int(redis_client.eval(ADMIT, len(keys), *keys, *args))
    except RedisError:
        logger.warning("Rate limiter unavailable; allowing request (Redis failure)")
        return None
    if wait:
        raise HTTPException(429, f"Usage limit reached. Please try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})
    return (active_key, token) if active_key else None


def release(lease):
    if lease:
        try:
            redis_client.zrem(*lease)
        except RedisError:
            logger.warning("Rate limit lease release failed; lease will expire")


def client_ip(request):
    # ProxyHopMiddleware already validated the configured right-hand hop.
    return request.client.host if request.client else "unknown"


async def limit_login(request: Request):
    payload = await request.json() if request.url.path.endswith("/login") else await request.form()
    if not hasattr(payload, "get"):
        return  # Leave invalid body validation to FastAPI.
    email = payload.get("email", payload.get("username", ""))
    admit([(bucket("login-email", email), 5, 300), (bucket("login-ip", client_ip(request)), 20, 60)])


async def limit_signup(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        return
    admit([(bucket("signup-email", payload.get("email", "")), 3, 3600),
           (bucket("signup-ip", client_ip(request)), 10, 3600)])


def limit_guest(request: Request):
    admit([(bucket("guest-ip", client_ip(request)), 10, 3600)])


def limit_chat(user=Depends(get_current_user)):
    identity = str(user["_id"])
    lease = admit([(bucket("chat-minute", identity), 10, 60), (bucket("chat-day", identity), 100, 86400)],
                  active_key=bucket("chat-active", identity), concurrency=2)
    try:
        yield
    finally:
        release(lease)


def limit_upload(user=Depends(get_current_user)):
    identity = str(user["_id"])
    lease = admit([(bucket("upload-hour", identity), 5, 3600)],
                  active_key=bucket("upload-active", identity), concurrency=1)
    try:
        yield
    finally:
        release(lease)
