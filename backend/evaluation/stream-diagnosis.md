# Stream investigation — 20 October 2026

## Confirmed observations

- `results/2026-10-20-live-web-100s.json`: complaint-status response headers were
  HTTP 200. First answer chunk arrived at 28.684 s; the client failed at 28.865 s
  with the allowlisted category `network_error`. It received 207 answer characters
  and no sources, verification or final route metadata. The old runner did not
  record the network exception subtype or server request ID; it cannot be
  recovered retroactively. No raw errors, answer text or credentials are saved.
- `app/services/ai_service.py`: retrieval precedes the Groq call. Sources,
  verification and the final route are emitted after generation. Thus partial
  answer text without sources is consistent with interruption before completion;
  it does not prove Tavily returned nothing or that the verifier caused failure.
- Groq generation exceptions are caught and converted to a sanitized `error`
  event. A controlled test injects a provider read error after a token and checks
  that behavior. The failed live sample had no such event. That does not prove
  Groq was healthy: a downstream break could also prevent delivery of the event.
- Controlled client tests distinguish an explicit provider-error event from a
  client transport read exception. Both count as failed, including partial text.
- A single diagnostic reproduction at UTC **07:56:17–07:56:22** completed:
  headers **0.310 s**, first answer **2.491 s**, full stream **4.298 s**, HTTP/1.1,
  **237 token events**, one sources event, one verification event and final route.
  No runtime change or deployment was made before this reproduction. Its success
  is not evidence of a fix and does not replace the benchmark failure.
- No controlled legal-answer quality, load, RAG Recall@k or uptime result follows
  from these observations. Seven of ten original benchmark chat attempts completed;
  this targeted reproduction stays outside that denominator.

## What remains unknown

The failing hop could be client connectivity, the hosting proxy, process restart
or another server failure. Current evidence cannot select among them. There is
no evidence sufficient to blame Tavily, prescribe a provider switch, or claim an
OOM/restart. The 65-second setup timeouts are a separate symptom, supported by
slow initial health and fast subsequent health requests; they are not the same
as this mid-answer interruption.

The maintainer subsequently supplied Render logs for the requested window. They
contain no per-entry timestamps or request correlation IDs in the pasted excerpt,
so matches below use sequence and metadata rather than unique request identity.

## Server-log findings supplied by the maintainer

- Every listed web retrieval returned five sources. The first five generation
  summaries match the benchmark sequence, including claim totals and grounding
  scores for the successful rows. The later single diagnostic matches ten claims
  and score 0.85.
- Groq returned HTTP 429 on three requests; SDK logs show retry waits of **7 s,
  24 s and 29 s**, followed by HTTP 200. This establishes provider throttling as
  a contributor to observed latency. It does not identify whether the quota was
  requests, input/output tokens, daily allowance or another dimension: the
  supplied logs contain no relevant response headers/body.
- The complaint-status position shows a 24-second retry and a subsequent
  generation-completed log with five sources and 13 claims. The client had a
  transport failure after partial text. A completed generator log does not prove
  all bytes were received by the client; the exact delivery failure remains
  unknown. No restart is shown between these five stream requests. The earlier
  graceful shutdown/startup is separate and does not establish a mid-stream crash.
- Retrieval progress heartbeats stop when retrieval completes. The subsequent
  synchronous Groq create/SDK retry wait does not emit application progress
  events. Thus a provider retry creates a silent interval. The recorded 24-second
  wait is not by itself proof of a proxy idle timeout: the client also received
  partial tokens afterwards.

The following work was subsequently approved and implemented locally. It was not
deployed when the earlier diagnostics ran, so it does not explain or replace
those outcomes. Post-deployment observations are recorded separately below.

## Generation hardening

- Existing chat model, prompt, token cap, retrieval and ownership checks unchanged.
  Complaint intake retains its own existing Groq client and behavior.
- Chat SDK automatic retries disabled. At most one explicit retry for pre-stream
  HTTP 429/500/502/503/504. Numeric/HTTP-date `Retry-After` (or milliseconds) is
  honored in full, with a one-second minimum; absent/invalid values use one second.
  If the wait exceeds the 30-second cap or remaining generation budget, return a
  sanitized busy error. No retry after partial tokens, to avoid duplicate answers.
- Code settings: `GROQ_GENERATION_DEADLINE_SECONDS=60`,
  `GROQ_REQUEST_TIMEOUT_SECONDS=15`, `GROQ_MAX_RETRY_WAIT_SECONDS=30` defaults.
  No `.env`, deployment file or hosting setting edited. The generation deadline
  starts after retrieval; the existing 75-second retrieval cap remains separate.
  The 15-second timeout applies to network phases, not the whole request; the
  stream controller enforces the separate 60-second total generation cap.
- One-second progress while waiting for the provider/retry. Frontend uses only
  allowlisted text, clearing it on token/error/Stop; no provider text becomes UI
  status or evidence/history. The final route still marks successful completion.
- Two daemon generation worker slots per process, no unbounded pending queue;
  each stream has a 32-event buffer. Caller timeout/disconnect sets cancellation,
  interrupts retry waits and discards late results. A running synchronous network
  call cannot be forcibly terminated: its slot is retained until that worker
  finishes and closes its stream. New requests fail busy rather than creating
  more workers while those slots are occupied. This is resource bounding, not a
  claim that any synchronous socket can be killed precisely at the deadline.
- Server-generated `X-Request-ID` correlates chat generation and transport
  lifecycle logs. New diagnostics accept only 32 lowercase hex characters from
  that header. Log fields are fixed phases, safe status/counters/wait durations
  and generated IDs; no prompts, user IDs, provider URLs/bodies or tokens.
  HTTPX INFO records for the Groq endpoint are filtered out.
- Twelve generation-runtime tests plus ASGI provider-disconnect and UI progress
  coverage check retry budgets, timeout, worker retention, cancellation, cleanup,
  safe logs and non-duplication. Full local suite: **320 backend + 42 frontend**,
  lint, build and compile checks. No new live performance claim is made.

### Subsequent post-deployment observation

The maintainer subsequently confirmed both deployments live. A new five-question
run at UTC **11:15:32–11:16:55** received the new request IDs and provider progress
on all requests. Four returned complete answers and sources; complaint-status
returned a structured `generation_busy` error at 23.368 s, with no partial text
and no transport exception. All five streams closed cleanly; maximum observed
initial/inter-event gap was 1.566 s. This is evidence of live progress/error
handling, not proof the original disconnect was fixed or quota limits removed.
Request `0a0bb77949204f16b4885d55a33cfb83` can be correlated with Render logs to
identify the exact final provider status. See the preserved artifact
`results/2026-10-20-postdeploy-web.json`. No failed row was replaced or rerun.

## Reproduction

With authorization for real provider usage:

```bash
cd backend
.venv/bin/python evaluation/diagnose_stream.py --live \
  --output evaluation/results/new-stream-diagnostic.json
```

One health check (100-second cap), one expiring guest after successful health,
one fixed question (90-second cap), no retries, no saved conversation. It records
only allowlisted event counts, elapsed times, HTTP protocol, sanitized failure
category/subtype and existing benchmark observations. The report is diagnostic,
not a benchmark or source of an SLA. Never overwrite reports or repeatedly create
guests to work around a usage limit. No fetch occurs during ordinary app requests.

Version 4 of `measure_resume.py` requires a final allowlisted route event before
counting successful completion. Clean EOF after tokens and sources but without
the final route now fails accounting. Existing seven historical successful rows
already contain a valid route, so this stricter check does not alter their counts.
