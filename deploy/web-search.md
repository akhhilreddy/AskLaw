# Web search providers

The default provider remains SearXNG. Tavily can replace only the web-search
transport without changing document RAG, ranking, streaming or verification.
Do not put a search API key in the frontend or a `VITE_` variable.

## Local backend

Add these to the existing, untracked `backend/.env` (never commit the key):

```dotenv
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=PASTE_YOUR_PRIVATE_KEY_HERE
```

Restart the backend process after changing settings. To use local SearXNG,
set `WEB_SEARCH_PROVIDER=searxng`; its existing URL/configuration is unchanged.

## Render API service

After the implementation is deployed, open **asklaw-api → Environment** and
add the same two variables. Paste the real key only into Render's value field,
then save/redeploy. No key or provider setting is needed in Netlify. Keep the
SearXNG service/configuration intact until hosted search is validated.

## Usage and failure behavior

- `TAVILY_MAX_QUERIES` defaults to 2 and accepts 1 or 2. Ordinary questions use
  one search; expanded research uses at most two per retrieval invocation.
- Requests explicitly use `search_depth=basic` and `auto_parameters=false`.
  Basic searches cost one credit each under Tavily's current API contract.
- There are no automatic POST retries or automatic SearXNG fallbacks. A failed
  request may already have used credit; repeated user questions use more credit.
- `TAVILY_TIMEOUT_SECONDS` defaults to 12 (maximum 30), with a 5-second maximum
  connect timeout and an async total deadline capped by the research deadline.
- Tavily bypasses the SearXNG readiness/wake-up check entirely.
- Missing keys, HTTP errors, quota/rate limits (429/432/433), malformed responses
  and timeouts produce the existing structured web-unavailable notice. Successful
  empty responses remain distinct from outages. Logs omit keys and error bodies.
- Result cards identify `tavily`; existing relevance/authority ranking still runs.
- Provider-generated answers and raw page content are not requested or used.
- This is a per-question request cap, not a shared monthly credit ledger. Monitor
  credits in Tavily and leave paid usage disabled for a strictly free demo.

Tavily integration does not remove the FastAPI service's own Render cold start.
API reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
