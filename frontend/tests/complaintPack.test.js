import assert from "node:assert/strict";
import test from "node:test";
import { applyImportBatch, applyImportSuggestion, importDecision, matchingImportEvents, complaintError, complaintPackHtml, emptyComplaint, sourceSelection } from "../src/services/complaintPack.js";

test("import applies one reviewed candidate with evidence and resets confirmation without mutating state", () => {
  const original = { ...emptyComplaint(), facts_confirmed: true, letter_text: "Old draft", seller_name: "Old seller" };
  const reference = { evidence_id: "e1", document_id: "d1", page_number: 1, start: 0, end: 20, page_text_sha256: "abc" };
  const candidate = { field: "seller_name", value: "New seller", reference };
  const next = applyImportSuggestion(original, candidate, { fieldChoice: "use" });
  assert.equal(next.seller_name, "New seller");
  assert.equal(original.seller_name, "Old seller");
  assert.equal(original.evidence.length, 0);
  assert.equal(next.facts_confirmed, false);
  assert.equal(next.letter_text, "");
  const event = { kind: "purchase", occurred_on: "2026-10-01", description: "Source", event_id: "t1" };
  const linked = applyImportSuggestion(next, { event, reference: { ...reference, evidence_id: "e2" } });
  assert.equal(linked.evidence.length, 1);
  assert.deepEqual(linked.events[0].evidence_ids, ["e1"]);
  assert.throws(() => applyImportSuggestion(linked, { event, reference }), /already in your timeline/);
  assert.throws(() => applyImportSuggestion({ ...original, evidence: Array(15).fill({}) }, candidate), /Evidence limit/);
  assert.throws(() => applyImportSuggestion({ ...original, events: Array(30).fill({}) }, { event, reference }), /Timeline limit/);
  assert.throws(() => applyImportSuggestion(original, { ...candidate, field: "facts_confirmed" }), /Unsupported/);
});

test("reviewed PDF matches attach source evidence to existing events, not duplicate events", () => {
  const data = { ...emptyComplaint(), events: [{ event_id: "n1", kind: "purchase", occurred_on: "2026-10-01", description: "My purchase account", evidence_ids: [] }] };
  const item = { suggestion_id: "s1", event: { event_id: "i1", kind: "purchase", occurred_on: "2026-10-01", description: "Purchase date: 2026-10-01" }, reference: { evidence_id: "e1", document_id: "d1", page_number: 1, start: 0, end: 20, page_text_sha256: "abc" } };
  assert.deepEqual(importDecision(data, item), { mergeTarget: "n1" });
  const next = applyImportBatch(data, [item]);
  assert.equal(next.events.length, 1);
  assert.equal(next.events[0].description, "My purchase account");
  assert.deepEqual(next.events[0].evidence_ids, ["e1"]);
  assert.equal(data.events[0].evidence_ids.length, 0);
  assert.equal(applyImportBatch(next, [item]).evidence.length, 1);
  assert.equal(applyImportBatch(data, [item], { s1: { mergeTarget: "new" } }).events.length, 2);
  const ambiguous = { ...data, events: [...data.events, { ...data.events[0], event_id: "n2" }] };
  assert.equal(importDecision(ambiguous, item).mergeTarget, "new");
  const mismatch = { ...item, event: { ...item.event, occurred_on: "2026-10-02" } };
  assert.deepEqual(matchingImportEvents(data, mismatch), []);
  assert.throws(() => applyImportBatch(data, [mismatch], { s1: { mergeTarget: "n1" } }), /conflicting date/);
});

test("unknown event dates change only after explicit reviewed matching; five-link limit remains", () => {
  const data = { ...emptyComplaint(), events: [{ event_id: "n1", kind: "delivery", occurred_on: null, description: "Arrived", evidence_ids: [] }] };
  const item = { suggestion_id: "s1", event: { event_id: "i1", kind: "delivery", occurred_on: "2026-10-03", description: "Delivery record" }, reference: { evidence_id: "e1", document_id: "d1", page_number: 1, start: 0, end: 20, page_text_sha256: "abc" } };
  assert.equal(importDecision(data, item).mergeTarget, "new");
  const next = applyImportBatch(data, [item], { s1: { mergeTarget: "n1" } });
  assert.equal(next.events[0].occurred_on, "2026-10-03");
  assert.equal(data.events[0].occurred_on, null);
  assert.throws(() => applyImportBatch({ ...data, events: [{ ...data.events[0], evidence_ids: ["a", "b", "c", "d", "e"] }] }, [item], { s1: { mergeTarget: "n1" } }), /five/);
});

test("PDF text defaults to keep mine and supports explicit replacement or edited combination", () => {
  const original = { ...emptyComplaint(), description: "My full account including refund refusal.", requested_resolution: "My refund request" };
  const item = { suggestion_id: "s1", field: "description", value: "The document's partial account.", reference: { evidence_id: "e1", document_id: "d1", page_number: 1, start: 0, end: 20, page_text_sha256: "abc" } };
  assert.equal(importDecision(original, item).fieldChoice, "keep");
  const kept = applyImportBatch(original, [item]);
  assert.equal(kept.description, original.description);
  assert.equal(kept.evidence.length, 1);
  assert.equal(applyImportBatch(original, [item], { s1: { fieldChoice: "use" } }).description, item.value);
  const combined = "My reviewed account plus selected document detail.";
  assert.equal(applyImportBatch(original, [item], { s1: { fieldChoice: "combine", combinedValue: combined } }).description, combined);
  for (const invalid of ["", "x".repeat(2001)]) assert.throws(() => applyImportBatch(original, [item], { s1: { fieldChoice: "combine", combinedValue: invalid } }), /combined text/);
  assert.equal(original.evidence.length, 0);
});

test("group import fails atomically on conflicting replacements or capacity overflow", () => {
  const original = emptyComplaint();
  const a = { suggestion_id: "a", field: "amount_inr", value: "12000.00", reference: { evidence_id: "e1", document_id: "d1", page_number: 1, start: 0, end: 20, page_text_sha256: "abc" } };
  const b = { ...a, suggestion_id: "b", value: "15000.00" };
  assert.throws(() => applyImportBatch(original, [a, b]), /one replacement/);
  assert.equal(original.amount_inr, "");
  assert.equal(original.evidence.length, 0);
  const full = { ...original, evidence: Array(15).fill({}) };
  assert.throws(() => applyImportBatch(full, [a]), /Evidence limit/);
  assert.equal(full.evidence.length, 15);
});

const pack = {
  pack_version: "1", title: "Synthetic complaint", facts: { facts_confirmed: true },
  checklist: [{ label: "Invoice", complete: false, required_for_draft: false }],
  timeline: [{ occurred_on: null, description: "Seller response date unknown", evidence_ids: ["e1"] }],
  evidence: [{ evidence_id: "e1", label: "Purchase record", available: true, filename: "sample.pdf", page_number: 2, start: 4, end: 17, quote: "INR 12000.00", document_id: "doc", page_text_sha256: "abc123" }],
  draft_ready: true, draft_letter: "User-reviewed fictional letter.", notices: ["No automatic filing."], disclaimer: "Legal information, not legal advice.",
};

test("source selection converts browser UTF-16 offsets to exact server code points", () => {
  const text = "🏠 Invoice: INR 12000.";
  const start = text.indexOf("INR");
  const result = sourceSelection(text, start, text.length);
  assert.equal(Array.from(text).slice(result.start, result.end).join(""), result.quote);
  assert.equal(result.start, start - 1);
  assert.equal(sourceSelection(text, 0, 0), null);
  assert.equal(sourceSelection("a".repeat(2001), 0, 2001), null);
  assert.equal(sourceSelection(text, 1, text.length), null);
  assert.equal(sourceSelection(text, 0, 1), null);
  assert.equal(sourceSelection(text, -1, 4), null);
});

test("export includes traceable evidence, user assertions, missing items and manual-only status", () => {
  const html = complaintPackHtml(pack);
  for (const value of ["not submitted", "Needs attention", "Date not supplied", "E1", "sample.pdf", "page 2", "abc123", "INR 12000.00", "not legal advice", "No automatic filing", "consumerhelpline.gov.in"]) assert.ok(html.includes(value), value);
  assert.equal(html, complaintPackHtml(pack));
});

test("untrusted source text, labels, events and letter edits cannot inject active HTML", () => {
  const attack = '<script>alert("x")</script><img src=x onerror=alert(1)>';
  const html = complaintPackHtml({ ...pack, title: attack, evidence: [{ ...pack.evidence[0], quote: attack, label: attack }], timeline: [{ ...pack.timeline[0], description: attack }] }, attack);
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("default-src 'none'"));
});

test("unavailable references never export stale quotes and unconfirmed drafts stay blocked", () => {
  const html = complaintPackHtml({ ...pack, draft_ready: false, evidence: [{ ...pack.evidence[0], available: false, quote: "STALE PRIVATE TEXT" }] }, "unconfirmed override");
  assert.ok(!html.includes("STALE PRIVATE TEXT"));
  assert.ok(!html.includes("unconfirmed override"));
  assert.ok(html.includes("Source unavailable"));
  assert.ok(html.includes("No letter generated"));
});

test("new complaint state is independent and errors are actionable text", () => {
  const first = emptyComplaint();
  first.events.push({});
  assert.deepEqual(emptyComplaint().events, []);
  assert.equal(emptyComplaint().facts_confirmed, false);
  assert.match(complaintError({ response: { data: { detail: "Reload before saving." } } }), /Reload/);
  assert.match(complaintError({ response: { data: { detail: [] } } }), /fields/);
  assert.match(complaintError({ code: "ERR_NETWORK" }), /refresh the case list/);
  assert.match(complaintError({ response: { status: 429, headers: { "retry-after": "60" } } }), /60 seconds/);
});
