# Consumer Complaint Pack - first release

A separate registered-account workspace at `/complaints` for **defective products
and refused refunds**. This prepares a user-reviewed complaint, not a court filing,
legal notice, enforceability opinion or guarantee of a refund. It does not revive
the abandoned scenario/playbook feature.

## What is implemented

1. Save and resume complaint facts, an optional INR transaction amount, requested
   resolution, and up to 30 timeline events. Dates can be left unknown; known
   dates are sorted without inferring dates or calculating deadlines.
2. Link up to 15 source excerpts from existing owned, indexed text-based PDFs.
   The page picker reuses the complete-page storage adapter already used by
   agreement review (50 pages / 100,000 characters, no scans or OCR). Highlight
   1-2,000 characters, label the record, and optionally link it to a timeline event.
3. Build a missing-information checklist and a deterministic complaint-letter
   draft. Required facts and explicit user confirmation gate the letter. Missing
   supporting documents are warnings, not invented evidence or mandatory legal
   filing requirements. No LLM, web search, embeddings or legal-rule engine is
   called to create the pack.
4. Edit the letter, optionally save the edit, then build again to resume/export
   it. HTML download requires an additional UI review acknowledgment. Open the
   downloaded file and Print → Save as PDF if desired. The pack contains an
   evidence index and excerpts, **not the original PDF attachments**.
5. Link to the official National Consumer Helpline for manual use. Nothing is
   submitted, emailed or represented as an integration with that service.

## Persistence and safety

### Describe -> review -> clarify -> prepare

The optional narrative intake at `POST /complaints/intake` accepts a 10-2,000
character description and explicit `consent_to_ai: true`. Only that description
is sent to the already configured Groq provider, using the existing
`openai/gpt-oss-120b` model. No PDF text, other complaint records, research history
or source URLs are added. The UI warns against unnecessary personal data. No
new environment variable, dependency or deployment setting is required.

The model proposes a supported category, field excerpts and up to eight events.
Strict JSON/schema checks and exact substring checks drop invented quotations;
an exact substring proves only what the user said, not semantic accuracy or
truth. INR amounts may be normalised deterministically (e.g. INR 12k -> 12000.00).
Unstated currencies and ambiguous/relative dates are left unknown. All candidates
are explicitly `user_report`, not PDF evidence. Out-of-scope classifications
show a normal-chat link. Human review remains mandatory, including the category.

The user reviews/selects suggestions, resolves conflicting fields and approves
replacement of existing values. Applying clears facts confirmation and the old
letter, without saving or adding evidence. Fixed local questions then ask only
missing required details, optional INR amount and dates for undated reported
events. Unknown answers can be skipped; skipped required fields still block the
letter. PDF import remains separate and dynamically removes answered questions;
its conflicting field values require review. The final form remains the common
review/edit surface before confirmation, explicit save and deterministic draft.

Pending narrative input, skipped questions and suggestions are session-local,
not saved, but survive list refresh (including refresh failures) and the first
save in the current workspace. New/open/delete actions intentionally reset this
session. Applied fields/events persist through the existing case save, as
user-confirmed accounts; narrative source snippets are not certified evidence
or a new provenance ledger. Reloading before saving loses pending intake.

Replacement, discard/open/new and delete confirmations are rendered inside the
workspace, not with browser alert/confirm dialogs. Replacement compares current
and suggested values; Cancel makes no change. Pending confirmations are bound to
the reviewed state and invalidated by edits. The browser-controlled close/reload
warning remains for unsaved changes; it cannot be replaced by in-page UI when
the user closes or reloads the tab.

Intake shares registered-account/chat rate limits. It has a 25-second hard async
deadline, 5-second connect timeout, 20-second phase timeouts and no SDK retries.
Provider failures, missing key, malformed JSON and timeout produce a sanitized
503 with manual-entry/PDF-import fallback. Descriptions and provider exception
bodies are not logged. No provider call runs during normal save/build/export.

### Review-first PDF import

`POST /complaints/import` accepts one or two owned document IDs, under the same
registered-account and chat quota gates. The source adapter enforces ownership,
indexed status and complete readable pages. No fetching, provider call, OCR or
database write occurs during extraction. Up to 60 candidates are returned.

The conservative parser recognises explicit Buyer/Customer, Seller, Seller contact,
Product/Item, Order reference/number/ID and INR Transaction amount/Total amount/Grand
total labels. Purchase/Invoice date, Delivery date, Buyer message and Seller reply
headings must have ISO dates (`YYYY-MM-DD`). Unrecognised layouts, dates and
currencies are omitted, not inferred. This is not arbitrary-invoice understanding.
Disagreeing values remain separate candidates. Explicit first-person accounts
beginning "I purchased/bought/received" and "I request" in dated Buyer message
blocks can be offered as description/remedy text, without paraphrasing or adding
entitlements. Otherwise those fields remain manual. Source messages can contain
unverified assertions; the tool never treats them as established facts.

Suggestions are grouped per document. Source excerpts can be expanded individually;
each retains PDF/page, code-point coordinates and page hash. Review selected rows
then apply the document as an atomic batch. A failed merge, cap or conflicting
replacement leaves the case unchanged. Changes to facts or review choices invalidate
the document review acknowledgment.

Nonempty fields default to **keep mine, add reference only**. Explicit alternatives
are use document value or (for description/remedy) combine in an editable preview
bounded to 2,000 characters. The original narrative is not silently replaced.

For events, a unique same-kind/same-known-date match is offered for review. The
user can instead add a separate event or select another compatible existing event.
Ambiguous matches and unknown dates do not default to a merge. An explicit reviewed
match preserves the existing wording, unions source links (maximum five), and can
fill a previously unknown date from the selected record. Conflicting known dates
are refused. Narrative intake also offers reviewed existing-event matches if PDFs
were imported first, preserving the existing evidence links. Matching is not a
finding that the document proves the event.

Applying clears facts confirmation and the old letter, without saving. Normal
save/build performs the existing live-source checks again. There is no new
environment setting, dependency or deployment requirement. No secrets or payload
text are logged.

The deterministic letter uses compact labelled chronology lines, explicitly
attributes short seller-response quotations, and references available evidence.
Long event wording is preserved in the full timeline/evidence index rather than
copied wholesale into the letter. Existing user-edited letters are unchanged.

- New MongoDB collection: `complaint_cases`, with an owner/updated-time index.
  Existing Mongo credentials are reused; there is no migration or new environment
  variable. Registered-user creation/saving creates the records normally.
- Stored data includes user-entered names/contact details/facts, timeline,
  optional user-edited draft, and source coordinates/page-text hashes. PDF quotes
  are not copied into complaint records. Deleting a complaint removes that record;
  separately uploaded PDFs remain in Documents until the user deletes them.
- Every list/read/update/delete/pack operation is owner-scoped. Both source-page
  access and each evidence lookup independently enforce PDF ownership and indexed
  status. Guests cannot use this private workspace; their existing quota and
  upload restrictions remain unchanged.
- A source quote is resolved from server-side page text, never accepted from the
  client. Save/build checks the selected page hash and bounds. Missing, failed,
  deleted or edited sources are marked unavailable on a subsequent build and their
  quotes omitted. A database outage returns a sanitized 503 rather than being
  misrepresented as missing evidence. Already downloaded packs are snapshots and
  cannot be revoked or automatically updated.
- Exact code-point offsets, page and document ID, and SHA-256 are preserved.
  Browser UTF-16 selections are converted safely. A checked quote proves location,
  **not that the source supports the user's assertion or a legal entitlement**.
- Full-document saves use optimistic revisions. Stale saves/deletes/builds get
  409; another tab cannot silently overwrite a newer saved revision.
- Storage and grouped source-check operations use 5-second Mongo operation
  deadlines. Creates, saves, deletes and builds share existing per-user chat limits
  (10/minute, 100/day, maximum 2 concurrent; existing Redis-down fail-open policy).
  GETs follow the existing authenticated read pattern. Lists cap at the newest
  50 cases and 100 PDF records. PDF import, saving and building do not call an LLM;
  the optional narrative intake consumes the configured Groq allowance.
- Exported values are escaped and the standalone HTML has a restrictive CSP.
  It distinguishes user-edited drafts from the template draft. No original file
  bundling, source-authenticity certification, automatic claim verification,
  compensation calculation or legal deadline calculation is provided.
- Saves are explicit, not automatic. Save before leaving the page. A timed-out
  create may already have succeeded: refresh Saved complaints before retrying.
  The first release has no exactly-once creation/idempotency ledger.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /complaints` | Latest 50 owned saved cases |
| `POST /complaints` | Save a new bounded `ComplaintCase` |
| `POST /complaints/import` | Suggest explicit fields and dated events from 1-2 owned PDFs, without saving |
| `POST /complaints/intake` | Consent-gated, user-reported suggestions from a brief description; no save |
| `GET /complaints/{id}` | Resume an owned case |
| `PUT /complaints/{id}` | Save `{revision, data}` using an atomic revision check |
| `DELETE /complaints/{id}?revision=N` | Delete only the owned matching revision |
| `POST /complaints/{id}/pack` | Build from saved `{revision}` with live source checks |
| `GET /complaints/documents` | List owned PDFs and source availability |
| `GET /complaints/documents/{id}/pages/{page}` | Retrieve one owned source page and its server hash |

## Local acceptance

1. Start/reload the existing API and frontend on this feature branch. Sign in to
   a registered account and select **Complaint Pack** in the sidebar or landing page.
2. Create a fictional complaint, e.g. a damaged laptop and a requested refund.
   Add the real/fictional facts yourself, without guessing dates or entitlement.
3. Optionally upload a selectable-text invoice/correspondence PDF in Documents,
   wait for Indexed, refresh lists, then highlight and label an excerpt here.
4. Add timeline events, link their excerpts, check your facts, then Save complaint.
5. Build the checklist/draft. Confirm missing information is flagged, edit the
   letter, save that edit if desired and build again. Review and download.
6. Reopen from Saved complaints. Test revision conflicts in two tabs, and remove
   a source PDF then rebuild to confirm that its quote is no longer available.

Tests: `backend/tests/test_complaint_pack.py` covers bounds, date handling,
confirmation gates, live-source hashes, missing sources, ownership, CRUD, stale
revisions, guests, rate responses and sanitized storage failures. Frontend tests
cover code-point selection, export escaping, unavailable evidence and error text.
No environment/deployment setting or existing auth/chat/retrieval behavior is
changed. Production deployment of this feature has not yet been verified;
repeat live acceptance on the deployed commit before treating it as released.

Validation of this working tree: **288 backend tests and 38 frontend tests passed**,
plus ESLint, Vite production build, Python compile checks and `git diff --check`.
Backend regression testing used the existing process-only SearXNG baseline for
legacy search tests; no `.env` was edited. Vite retains its large-bundle warning.
Desktop (1440px) and mobile (390px) smoke checks exercised facts, exact source
selection, saving, building, editing, reopening and downloading without page
errors or horizontal overflow. Browser API responses were synthetic and pack
generation used the actual backend builder; no real account/cloud record was
created by these checks. The running local API schema advertises the new routes.
An initial live registered-account run also passed real Groq intake, two uploads,
indexing, saving, building, exporting and reopening, in about 10.4 seconds locally.
It created only clearly labelled fictional records and exposed the workflow issues
addressed below; this is not a cold-start latency guarantee.

Import acceptance: the two fictional complaint PDFs produced 12 suggestions,
including buyer account/request text and four dated events. Desktop (1440px) and
mobile (390px) checks applied them into 10 distinct evidence references, confirmed
facts, saved and built a letter. API responses were intercepted offline; extraction
used the actual PDF text/parser and generation used the real pack builder. No
cloud writes occurred. `test_complaint_import.py` covers exact source coordinates,
buyer/seller separation, wrapped paragraphs, invalid/unknown values, conflicts,
output bounds, authentication/guest gates and source-adapter errors. Frontend
tests cover reference reuse, confirmation reset, duplicate events and import caps.

Narrative intake tests cover consent, authentication/guest refusal, shared 429
headers, exact excerpts, unknown currency/dates, out-of-scope output, model schema
failures, cancellation at the hard deadline, bounded SDK configuration and
sanitized errors. Desktop/mobile browser checks exercise consent -> proposed
facts -> review -> one-at-a-time questions -> unknown-date skip -> confirmation
-> save -> real pack builder, plus fresh-case reset and unsupported/outage flows.
Provider and API responses in regression suites are mocked offline. Separate live
checks exercised real Groq, including differing amounts and an out-of-scope request,
plus registered-account persistence and actual missing-question handling. The
running localhost API schema includes both `/complaints/intake` and
`/complaints/import`.

Workflow refinements: `frontend/tests/complaintWorkflow.browser.mjs` exports a
Playwright regression helper taking a Page plus fictional narrative/PDF fixtures
and a backend-builder callback. It needs no application dependency change. The
desktop/mobile run verifies successful/failed refresh, a pending answer and skipped
questions surviving first save, per-document review invalidation, preserved
narrative, source links without duplicate events, and both import orders. Replaying
the original live fictional data now yields **five events and ten source references**
instead of nine events. Node tests cover atomic batches, conflicting/ambiguous
dates, edited combinations, link/cap limits and reverse-order matching. Backend
tests cover compact attributed letters, full quote retention and omission of
unavailable source citations. The post-refinement real-account rerun could not
start because the signed-in test window was closed; no additional record was
created. Repeat live acceptance before deploying these refinements.
