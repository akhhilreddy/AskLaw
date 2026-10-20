# AskLaw evaluation harness

The curated cases cover document, web, hybrid, isolation, and claim-support
behavior. The harness prints individual observations and counts; it deliberately
does not manufacture an aggregate accuracy percentage.

Offline routing and deterministic verification evaluation:

```bash
cd backend
.venv/bin/python evaluation/run_evaluation.py
```

Live retrieval evaluation against an already-running local stack:

```bash
cd backend
.venv/bin/python evaluation/run_evaluation.py --live \
  --user-id USER_ID \
  --other-user-id SECOND_USER_ID \
  --document-id DOCUMENT_ID \
  --expected-filename document.pdf
```

The live mode reports whether retrieval returned evidence, the selected route,
source filenames, expected-source presence, and document-isolation behavior.
It does not call Groq or claim that an answer is legally correct.

## Reproducible résumé measurements

`measure_resume.py` adds bounded measurements, without changing application
behavior, environment files or deployment settings. The fixed inputs and expected
intake fields are in `resume_cases.json`. Never edit the expected values to fit
a provider response after a run; preserve failures and record a new report for
each later run.

Offline routing/verification only (no provider calls or guest creation):

```bash
cd backend
.venv/bin/python evaluation/measure_resume.py \
  --output evaluation/results/my-offline-run.json
```

Opt-in live run against **the existing AskLaw production API**, plus the local
intake service using the real configured Groq account:

```bash
cd backend
.venv/bin/python evaluation/measure_resume.py --live \
  --output evaluation/results/my-live-run.json
```

Choose a fresh output filename each time; existing reports are never overwritten.
Run only with the owner's authorization. This is not a load test. The command:

- Performs one API health preflight. Its preceding idle/cold state is unknown.
- Creates one ordinary, expiring guest and makes at most five sequential public
  `/chat/stream` requests, without creating conversations or uploading documents.
  The guest uses its normal quota and expires through existing policy; no extra
  guest is created to retry/bypass the quota.
- Sends six checked-in **fictional** descriptions through real Groq intake,
  directly from the local service. This does not measure deployed registered
  auth, database persistence or browser rendering. It reuses the existing
  `GROQ_API_KEY`; no credentials are printed or added to reports.
- Consumes provider allowance: up to ten Tavily searches if the deployed API uses
  its current two-query cap, plus chat generation and six intake model calls.
  Application/SDK retry policies remain unchanged; the harness does not rerun
  failed cases. Do not run repeatedly just to obtain a better-looking result.
- Records all planned cases, including errors and setup failures. No answer
  bodies, cookies, tokens, user IDs, raw provider errors or source URL query
  strings are saved. Public source domains and answer hashes are retained.

Harness version 2 additionally hashes its own source and the legacy cases file,
retains safe failure categories/status codes, and retains partial stream timings
without counting an interrupted stream as successful. A process-local wrapper
observes failures from the **real** Groq extractor before the intake service
sanitizes them; it does not fake responses or change SDK requests, retry policy,
timeouts or the deployed application. The original callable is restored after
each case. Tests verify that restoration and that no exception bodies are saved.
The 19 October version-1 report is preserved unchanged, including its missing
failure categories; later instrumentation cannot retroactively diagnose it.

Version 3 adds an explicit web-only mode and a bounded health preflight setting:

```bash
cd backend
.venv/bin/python evaluation/measure_resume.py --live --web-only \
  --health-timeout-seconds 100 \
  --output evaluation/results/my-web-100s-run.json
```

The default remains 65 seconds; values must be integers from 1 to 120. The chosen
budget and live section are recorded in `measurement_settings`. A larger setup
budget is a different condition, not evidence of faster startup. Web-only mode
skips intake entirely, creates at most one ordinary guest after health succeeds,
and retains the existing five sequential questions and 90-second per-chat cap.
It does not change application, SDK or deployment timeouts, retry failed cases,
or overwrite earlier reports. Each explicit live invocation can consume quota;
never use it to rotate guests around a limit.

### Metric definitions

| Metric | Definition / boundary |
| --- | --- |
| Answer-with-sources completion | HTTP 200, nonempty answer and sources, with no stream error, outage notice or fixed insufficient-evidence response; version 4 also requires the final route event. This checks protocol completion/source presence, **not answer correctness or source relevance**. |
| First answer chunk | Client time from POST until the first nonempty `token` event. Progress/heartbeats do not count. It is not tokenizer-based token throughput. |
| Completion latency | Client wall time through stream closure, including network/server/provider time. Successful latencies are reported separately from all-attempt latencies. A fast failure is not a fast answer. |
| Scope checks | Agreement with six developer-authored supported/out-of-scope labels. Unavailable cases remain in the planned denominator. |
| Exact field checks | Set match after case/whitespace/trailing-punctuation normalization for buyer, seller, product, order reference and INR amount. Expected values are fixed in the fixture. Descriptions/remedies and semantic equivalence are not scored. |
| Conditional field precision / recall | `TP/(TP+FP)` and `TP/(TP+FN)` **only for completed intake responses**; always publish TP/FP/FN, completed count and failures. Do not present this as overall extraction accuracy when calls fail. |
| End-to-end expected-fact recall (version 2) | Correctly returned scored fields divided by **all planned expected field-value targets**. Unavailable calls contribute no returned facts, but their gold targets remain in the denominator. |
| Quote fidelity | Whether returned suggestion excerpts occur in the fictional input. The application already enforces this, so a high value does not independently prove extraction quality. |
| Grounding observation | Existing deterministic evidence-support score; not expert legal accuracy. |

Use sample count, median and min/max for these small runs, not p95/p99, uptime
SLAs, throughput or scaling claims. There is no held-out expert-reviewed legal
dataset, live private-document retrieval ground truth, Recall@k or concurrency
capacity measurement in this benchmark.

### Recorded run — 19 October 2026

Raw artifact: [2026-10-19-live-resume.json](results/2026-10-19-live-resume.json).
The report records application base commit `e97200f`, uncommitted harness status,
fixture SHA-256, Python version, UTC run window and per-case outcomes. The deployed
commit is not exposed by `/health`, so the report does not assume it equals the
local commit.

- Web: **3/5** attempts completed with answers and sources. For those three only,
  median first answer was **7.178 s** and median completion **7.506 s**, with
  completion ranging **7.121–29.966 s**. Two requests failed. The first harness
  records them as `request_failed` without retaining the specific exception
  category, so their root cause is **unknown**, not proven server overload.
- Intake: **2/6** calls completed; four returned the service's sanitized unavailable
  outcome. Both completed scope checks passed. Only **three expected scalar facts**
  were evaluated on completed responses (3 TP, 0 FP, 0 FN), all from the mixer
  fixture. This is **not sufficient to advertise “100% extraction accuracy.”**
- Offline: **7/7 routing** and **5/5 claim-support** fixtures passed. These are
  small curated checks, not general legal/model accuracy.

A separate diagnostic after the run made three successful public health GETs
(HTTP 200) and one successful real Groq extraction (2.716 s). This does not repair,
replace or explain the earlier failures and is not included in the benchmark
sample. No application fix or further guest benchmark was performed.

The appropriate next step is diagnosing intermittent request/provider failures
and then collecting a larger, independently labelled evaluation—not claiming
production capacity or high accuracy from this run. Benchmark accounting is
covered by `tests/test_resume_metrics.py`; those tests use no network.

### Reproduction — 20 October 2026

Raw artifact: [2026-10-20-live-resume.json](results/2026-10-20-live-resume.json).
The fixed-case SHA-256 matches the 19 October report exactly. Harness version 2
has additional diagnostic/accounting fields; neither the application behavior nor
the gold inputs/expected answers were changed to improve results.

| Measurement | Result |
| --- | --- |
| Public API setup | Health preflight timed out at **65.007 s**. No guest was created and no web chat POST was attempted. All five planned questions are `not_run_setup_failed`; this is not five failed chat responses. |
| Real Groq intake completion | **6/6** local-service calls completed. |
| Scope labels | **6/6** passed: four supported product complaints and two out-of-scope descriptions. |
| Normalized exact field-value matches | **12 TP, 0 FP, 0 FN**, over 12 planned scored targets across the four supported fixtures. Conditional precision, recall and end-to-end expected-fact recall are 1.0 **on this fixed sample only**. |
| All six intake responses | Median **1.875 s**, range **1.421–2.742 s**; includes two out-of-scope responses. |
| Four supported intake responses | Median **2.247 s**, derived from the four supported fixture IDs; not a deployed browser/API latency. |
| Quote fidelity | **34/34** returned excerpts occur in the input; this is enforced by application validation, not independent semantic/legal accuracy. |
| Offline cases | The same **7/7** routing and **5/5** claim-support fixtures passed. |

The earlier 19 October **3/5 web completion and 2/6 intake completion** remain part
of the evidence. Do not remove them or claim that the improved intake snapshot
proves a reliability fix: the app was not changed and conditions were uncontrolled.
The latest API preflight timeout was observed by this client; a server/provider,
cold-start or network root cause has not been established. Do not label it as a
proven server crash or overload.

To reproduce the supported-only latency from saved artifacts, without network:

```bash
cd backend
.venv/bin/python -c 'import json,statistics; from pathlib import Path; c=json.loads(Path("evaluation/resume_cases.json").read_text()); r=json.loads(Path("evaluation/results/2026-10-20-live-resume.json").read_text()); ids={x["id"] for x in c["intake_cases"] if x["supported"]}; values=[x["elapsed_seconds"] for x in r["intake"]["rows"] if x["id"] in ids and x["status"]=="ok"]; print(len(values), round(statistics.median(values), 3))'
```

Benchmark-accounting coverage now includes **11 offline tests**; the full suite
passed **299 backend + 38 frontend tests**, plus compile checks, ESLint and the
production build. No environment/deployment setting was edited and no application
runtime source file was changed for these measurements.

### Follow-up measurements — 20 October 2026

These are new reports, not replacements for the failures above. The fixture
SHA-256 remains unchanged. No merge, push, environment edit or deployment was
performed for these runs. Local frontend readiness commit `2910ddc` does not
change the production API and was not deployed during either follow-up.

1. [Same-budget follow-up](results/2026-10-20-live-resume-followup.json), harness
   version 2, UTC **07:43:35–07:44:58**: health timed out at **65.010 s**, before
   guest creation; all five questions remain `not_run_setup_failed`. Six intake
   calls completed, scope **6/6**, scalar fields **12 TP / 0 FP / 0 FN**. Median
   supported-case extraction **2.283 s** (n=4); all-response median **2.231 s**
   (n=6), range **1.068–2.477 s**. Excerpts **35/35** exact; date checks passed
   in all six responses. These repeat the same inputs, not six independent new
   scenarios. Quotes and date checks are partly application-enforced.
2. [Web-only follow-up](results/2026-10-20-live-web-100s.json), harness version 3,
   UTC **07:45:57–07:47:37**: explicitly recorded **100-second** health budget;
   actual health response **0.364 s**, therefore no evidence here that the larger
   budget rescued a cold start. One ordinary guest, five sequential questions,
   no saved conversations, no intake calls. **4/5** completed with answers and
   five sources each. The complaint-status request failed with sanitized
   `network_error` at **28.865 s**, after **207 answer characters** but before
   sources/route/verification arrived. Partial output is not completion, and
   the category alone cannot locate the failing network/server hop.

| Successful web-only timings (n=4) | Median | Range |
| --- | --- | --- |
| First nonempty answer chunk | 8.505 s | 3.980–36.808 s |
| Complete stream | 10.310 s | 4.918–39.414 s |

All-attempt elapsed median is **14.144 s** (n=5); it includes an interruption,
so it is not an answer-latency guarantee. Source domains include official sites
for the helpline question but also blogs, Wikipedia, Quora and YouTube in other
questions. Counted source presence is **not** expert-assessed source quality or
legal correctness. No accuracy, p95, uptime or concurrent-capacity claim follows.

Across the 19 October and later web-only run there are **7 completed streams out
of 10 actual chat attempts**. Two other runs failed setup and attempted zero
chats. This pooled count is descriptive only: uncontrolled conditions, repeated
questions and different setup budgets, not ten independent legal tasks or an SLA.

After the version-3 options, full regression checks passed **302 backend + 41
frontend tests** (343 total), including **14** benchmark-accounting tests. Lint,
production build, compile checks and diff whitespace checks passed; existing
Vite chunk-size warning remains. No failed benchmark case was retried in place.

### Targeted stream investigation

See [stream-diagnosis.md](stream-diagnosis.md) and
[the single diagnostic artifact](results/2026-10-20-stream-diagnostic.json).
This separate reproduction succeeded in 4.298 s; it does not replace the failed
benchmark row or establish a fix. Four controlled tests cover transport failure,
provider error events, successful metadata completion and server-side Groq error
sanitization. A fifteenth benchmark-accounting test rejects clean EOF before the
final route. Harness version 4 requires that event for completion; all historical
successful rows already contain it. Full checks now pass **307 backend + 41
frontend tests (348 total)**, lint, build and compile checks at that stage.
Runtime application, environment and deployment configuration had not changed
when those diagnostic measurements were made.

Subsequently approved local generation hardening is described in
[stream-diagnosis.md](stream-diagnosis.md#local-generation-hardening-not-yet-deployed).
It now passes **320 backend + 42 frontend tests (362 total)**, lint/build/compile
checks, including deterministic 429/deadline/disconnect tests. It has not been
deployed or live-benchmarked. Earlier artifacts remain unchanged; do not claim
they demonstrate the new retry/progress policy's production behavior.
