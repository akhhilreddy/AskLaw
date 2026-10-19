import test from "node:test";
import assert from "node:assert/strict";
import { agreementError, agreementReportHtml, escapeHtml } from "../src/services/agreementReport.js";

const source = { document_id: "doc-a", page_number: 2, start: 0, end: 12, quote: "Rent INR 100.", page_text_sha256: "abc123" };
const review = { analysis_version: "1", title: "Rental.pdf", extracted_text_sha256: "text123", terms: [{ kind: "rent_and_payment", mentions: [source] }, { kind: "lock_in", mentions: [] }], limitations: ["No enforceability opinion."], disclaimer: "AskLaw provides legal information, not legal advice." };

test("review export keeps exact quotes, references, text hashes and limits", () => {
  const html = agreementReportHtml(review);
  for (const text of [source.quote, "page 2", "0–12", "abc123", "text123", "not a finding", review.disclaimer, review.limitations[0], "Save as PDF"]) assert.ok(html.includes(text), text);
  assert.equal(html, agreementReportHtml(review));
});

test("untrusted quotes, titles and metadata cannot inject HTML into download", () => {
  const attack = '</pre><script>alert("x")</script><img src=x onerror=alert(1)>';
  const html = agreementReportHtml({ ...review, title: attack, terms: [{ kind: "rent_and_payment", mentions: [{ ...source, quote: attack, document_id: attack }] }] });
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("default-src 'none'"));
  assert.equal(escapeHtml(`&<>"'`), "&amp;&lt;&gt;&quot;&#39;");
});

test("comparison download preserves both sides and identifies synthetic sample", () => {
  const report = { analysis_version: "1", before: { title: "Old", extracted_text_sha256: "old" }, after: { title: "New", extracted_text_sha256: "new" }, summary: { changed: 1 }, changes: [{ kind: "changed", before: [source], after: [{ ...source, document_id: "doc-b", quote: "Rent INR 200." }] }], limitations: review.limitations, disclaimer: review.disclaimer };
  const html = agreementReportHtml(report, true);
  for (const text of ["SYNTHETIC SAMPLE", "NOT A LEGAL TEMPLATE", "Rent INR 100.", "Rent INR 200.", "doc-a", "doc-b", "Text changed: 1"]) assert.ok(html.includes(text), text);
  assert.match(agreementReportHtml({ ...report, changes: [] }), /does not prove the signed PDFs are identical/);
});

test("errors preserve actionable reupload and 429 retry information", () => {
  assert.equal(agreementError({ response: { data: { detail: "Re-upload this PDF." } } }), "Re-upload this PDF.");
  assert.match(agreementError({ response: { status: 429, headers: { "retry-after": "60" } } }), /60 seconds/);
  assert.match(agreementError({ code: "ERR_NETWORK" }), /connection/);
  assert.equal(typeof agreementError({ response: { data: { detail: [{ msg: "bad" }] } } }), "string");
});

test("review export distinguishes clause candidates from clipped context without trusting labels", () => {
  const report = { ...review, terms: [{kind: "rent_and_payment", mentions: [
    {...source, scope: "clause_candidate"},
    {...source, scope: "context_excerpt", is_partial: true},
    {...source, scope: '<script>fake scope</script>'},
  ]}] };
  const html = agreementReportHtml(report);
  assert.ok(html.includes("Clause candidate"));
  assert.ok(html.includes("Local context excerpt"));
  assert.ok(html.includes("Clipped excerpt"));
  assert.ok(!html.includes("<script>"));
});
