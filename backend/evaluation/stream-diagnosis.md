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

Next approved work: bounded generation retries/deadline, provider-wait progress,
disconnect-safe cleanup and sanitized request correlation. Runtime implementation
will be committed separately from these measurements. No performance improvement
is claimed from the diagnostic reproduction.

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
