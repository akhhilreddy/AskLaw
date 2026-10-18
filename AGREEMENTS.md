# Before You Sign — agreement review and comparison

## Product decision

Start with English text-based rental agreements. One product, three planned
capabilities: source-linked key terms, two-version comparison, and an exportable
comparison report. Consumer-complaint preparation and other scenario workflows
are not part of this implementation. At the user's request the local scenario
branch was deleted and this branch starts at the pre-scenario `95c35dd` baseline.
Scenario work is recoverable in the named local Git recovery stash; it is not
part of the active application. The unrelated authentication/research flows stay.

This is document analysis, not an Indian-law enforceability opinion. Do not
invent a national tenancy rule, classify a clause as illegal, guarantee that an
agreement is safe, or infer that an unidentified term is absent.

## Implemented first slice

- `backend/app/schemas/agreement.py`: complete ordered page input, strict types,
  50-page/100,000-character bounds and rejection of blank/corrupt pages.
- `backend/app/services/agreement_analysis.py`: keyword-assisted candidate
  mentions for deposit, rent/payment, notice, lock-in, termination, renewal,
  deductions/charges and disputes/jurisdiction. Each quote retains document ID,
  page, character offsets and a page-text hash. These are mentions, not complete
  clause interpretations or legally required terms.
- Deterministic passage-group diff: additions, removals, replacements and
  whitespace-only changes. Original quotes and literal currency/time tokens
  remain visible. It does not yet perform semantic clause matching, PDF
  annotation, financial calculations or deadline calculations.
- Deterministic UTF-8 JSON report export with limitations and disclaimer.
- Offline synthetic tests, without a model, source fetch or real user document.

The hashes identify extracted text, NOT original PDF bytes or signature
authenticity. Unchanged extracted text does not prove equivalent signed files.
No LLM decides whether a term is lawful; user document text is never executed.

### Focused review excerpts (review analysis version 2)

Key-term review now prefers explicit numbered/named sections rather than
repeating a whole extracted page under each heading. Within unstructured text,
it selects the matching sentence and immediately following qualifying sentences.
Multiple hits picking the same or an already-covered source range are deduplicated
per term/page. The same clause may legitimately appear under notice and
termination if it addresses both. Page references, exact code-point offsets and
text hashes always refer to the untouched extracted page text.

The UI and exported report distinguish **Clause candidate**, **Local context
excerpt**, and **Clipped excerpt**. Sections are structural candidates, not
guaranteed semantic/legal clauses. Long excerpts remain capped at 2,000 characters;
unidentified terms are not called absent. Comparison analysis stays version 1
and keeps its existing passage-group diff behavior. No re-upload is necessary
for documents with stored page text: rerun Find key terms and download a new
report. Previously downloaded reports are not rewritten.

## Usable first release

- Protected `/agreements` page, linked from the landing page and both sidebar
  layouts. Two tools: **Compare versions** and **Find key terms**.
- Owner-scoped `GET /agreements/documents` (latest 100 uploads),
  `POST /agreements/review` (`document_id`), and `POST /agreements/compare`
  (`before_id`, `after_id`). Accepts IDs only, not client-supplied document text,
  ownership or hashes. Each version is independently looked up by owner.
- Every new upload additionally stores validated, complete extracted page text
  as `agreement_pages` with version/eligibility metadata, only within the
  50-page/100,000-character analysis bounds. Original chunking, queueing and
  indexing status transitions are unchanged. Ineligible PDFs still follow the
  existing research flow. Review requires `indexed` status; no overlapping RAG
  chunks are stitched together to fabricate page references.
- Legacy uploads without page text explicitly require re-upload for this tool.
  Missing/scanned/corrupt pages fail closed; there is no automatic OCR.
- Mongo reads have a 5-second operation deadline and sanitized 503 errors.
  New review/compare/sample operations reuse shared chat rate limits: 10/min,
  100/day and 2 concurrent per account, with existing Retry-After behavior.
  This adds no separate quota setting. Redis fail-open behavior is unchanged.
- Registered accounts review their uploads. Guests keep their existing web-only
  upload restrictions; they can view the synthetic sample using
  `GET /agreements/demo`. This sample performs no database read or AI request,
  does not consume a guest web question, but shares account request rate limits.
- Source quotes include page, document ID, exact code-point offsets (zero-based,
  end-exclusive) and page-text SHA-256. Keyword misses are not called omissions.
- Human-readable HTML download, including quotes, references, extracted-text
  identities, limitations and disclaimer. Open locally and use browser
  **Print → Save as PDF**. No built-in PDF/DOCX generation or separate persisted
  report history is claimed. All untrusted report values are HTML-escaped;
  exports contain no scripts, external resources, tokens or API keys.

No auth, chat, RAG, Celery, embeddings, environment variables or deployment
configuration were changed. Upload storage has the additive page-text fields
described above; no migration/new collection or dependency is required.

## Try it locally

1. Start the existing backend/frontend as usual, with your usual local settings.
   A running backend needs to reload/restart to register the new endpoints.
2. Sign in (or continue as guest), then select **Before You Sign** in the sidebar.
3. Press **Try sample**. It is explicitly fictional, not a legal template:
   deposit INR 10,000 → INR 15,000; notice 30 → 90 days.
4. Switch to **Find key terms** and try the sample again. Inspect the source
   reference and the honest "not identified" states.
5. Download the report; open it locally and print/save as PDF if desired.
6. For your own versions, use a registered account, upload two English,
   selectable-text rental PDFs through Documents, wait until indexed, then
   return here and refresh the library. Select original and revised versions.

This feature does not certify signatures, preserve original PDF layout, calculate
money owed or assess Indian/state-law validity. Semantic clause interpretation
and risk assessments need a separate design/evaluation, not a renamed text diff.

## Run feature tests

From this checkout's `backend` directory, with a compatible existing Python
environment containing Pydantic:

```bash
python -m unittest tests.test_agreement_analysis tests.test_agreement_api -v
```

Tests cover exact quotes, bounded input, malicious text, deterministic changes,
real in-memory PDF extraction through the owned comparison API (queue/DB faked),
cross-user denial, guests, legacy documents, partial pages, database outages and
rate limits. Frontend Node tests cover safe, source-linked exports and errors.
Live Mongo/Celery processing and deployment remain separate acceptance checks.

Validation of the focused-excerpt working tree: 256 backend tests passed with a process-only
SearXNG provider baseline for the legacy search tests (the local `.env` was not
changed); 23 frontend tests passed; ESLint, Vite build, compile checks and
`git diff --check` passed. Vite reports the existing large-bundle warning.
Desktop (1440px) and mobile (390px) browser smoke checks used synthetic backend
reports with mocked API responses: selection, comparison, sample, download and
key-term review worked, with no page exceptions or horizontal overflow. This is
not a claim that live Mongo/Celery or the deployed feature was exercised.

On both generated rental PDFs, focused review reduced the deposit passage from
809 to 143 characters and the notice passage from 953 to 194 characters, with
unchanged page-text hashes and exact source offsets. Empty page titles were
excluded. The previously downloaded HTML report is not modified automatically.
