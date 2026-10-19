import test from "node:test";
import assert from "node:assert/strict";
import { emptyComplaint } from "../src/services/complaintPack.js";
import { applyNarrativeSuggestions, intakeQuestions, applyIntakeAnswer } from "../src/services/complaintIntake.js";

const candidate = (field, value) => ({ origin: "user_report", field, value, quote: value });

test("reviewed user reports never become PDF evidence or confirmed facts", () => {
  const data = { ...emptyComplaint(), facts_confirmed: true, letter_text: "Old letter" };
  const event = { event_id: "n1", kind: "delivery", description: "Laptop arrived damaged", occurred_on: null, evidence_ids: ["forged"] };
  const next = applyNarrativeSuggestions(data, [candidate("product", "Laptop"), { origin: "user_report", event }]);
  assert.equal(next.product, "Laptop");
  assert.equal(next.facts_confirmed, false);
  assert.equal(next.letter_text, "");
  assert.deepEqual(next.evidence, []);
  assert.deepEqual(next.events[0].evidence_ids, []);
  assert.equal(data.product, "");
  assert.equal(applyNarrativeSuggestions(next, [{ origin: "user_report", event }]).events.length, 1);
});

test("narrative added after PDFs can use a reviewed existing event without losing source links", () => {
  const data = { ...emptyComplaint(), events: [{ event_id: "pdf1", kind: "delivery", occurred_on: "2026-10-03", description: "Existing delivery record", evidence_ids: ["e1"] }] };
  const suggestion = { suggestion_id: "s1", origin: "user_report", event: { event_id: "n1", kind: "delivery", occurred_on: "2026-10-03", description: "It arrived damaged" } };
  const next = applyNarrativeSuggestions(data, [suggestion], { s1: { mergeTarget: "pdf1" } });
  assert.equal(next.events.length, 1);
  assert.deepEqual(next.events[0].evidence_ids, ["e1"]);
  assert.equal(next.events[0].description, data.events[0].description);
  assert.equal(applyNarrativeSuggestions(data, [suggestion], { s1: { mergeTarget: "new" } }).events.length, 2);
  assert.throws(() => applyNarrativeSuggestions(data, [{ ...suggestion, event: { ...suggestion.event, occurred_on: "2026-10-04" } }], { s1: { mergeTarget: "pdf1" } }), /conflicting date/);
});

test("conflicts require one choice and invalid origins or excess events fail atomically", () => {
  const data = emptyComplaint();
  assert.throws(() => applyNarrativeSuggestions(data, [candidate("amount_inr", "12000"), candidate("amount_inr", "15000")]), /conflicting/);
  assert.equal(data.amount_inr, "");
  assert.throws(() => applyNarrativeSuggestions(data, [{ ...candidate("product", "Laptop"), origin: "document" }]), /Invalid/);
  assert.throws(() => applyNarrativeSuggestions(data, [candidate("facts_confirmed", true)]), /Unsupported/);
  assert.throws(() => applyNarrativeSuggestions({ ...data, events: Array(30).fill({ kind: "other" }) }, [{ origin: "user_report", event: { kind: "delivery", description: "new" } }]), /limit/);
});

test("questions only ask missing values and update when PDF import fills them", () => {
  const data = { ...emptyComplaint(), buyer_name: "Buyer", product: "Laptop" };
  assert.equal(intakeQuestions(data)[0].field, "seller_name");
  const fromPdf = { ...data, seller_name: "Seller" };
  assert.equal(intakeQuestions(fromPdf)[0].field, "seller_contact");
  assert.equal(intakeQuestions(fromPdf, ["seller_contact"])[0].field, "description");
  assert.equal(fromPdf.seller_contact, ""); // Skipping doesn't invent a value.
});

test("answers validate amount and actual dates, never infer unknown ones", () => {
  const data = { ...emptyComplaint(), events: [{ event_id: "n1", occurred_on: null }] };
  const question = { key: "amount_inr", field: "amount_inr", maxLength: 13 };
  assert.deepEqual(applyIntakeAnswer(data, question, "12000.00"), { amount_inr: "12000.00" });
  for (const invalid of ["", "12k", "1,000", "-10"]) assert.throws(() => applyIntakeAnswer(data, question, invalid));
  const dateQuestion = { eventId: "n1" };
  assert.throws(() => applyIntakeAnswer(data, dateQuestion, "2026-02-30"));
  assert.throws(() => applyIntakeAnswer(data, dateQuestion, "yesterday"));
  assert.equal(applyIntakeAnswer(data, dateQuestion, "2026-10-03").events[0].occurred_on, "2026-10-03");
  assert.equal(data.events[0].occurred_on, null);
});
