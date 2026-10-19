import { escapeHtml } from "./agreementReport.js";

export function emptyComplaint() {
  return { title: "New consumer complaint", issue_type: "defective_product", buyer_name: "", seller_name: "", seller_contact: "", product: "", order_reference: "", amount_inr: "", description: "", requested_resolution: "", facts_confirmed: false, events: [], evidence: [], letter_text: "" };
}

export function matchingImportEvents(data, suggestion) {
  if (!suggestion.event) return [];
  return data.events.filter((event) => event.kind === suggestion.event.kind
    && (!event.occurred_on || !suggestion.event.occurred_on || event.occurred_on === suggestion.event.occurred_on));
}

export function importDecision(data, suggestion) {
  if (suggestion.event) {
    const exact = matchingImportEvents(data, suggestion).filter((event) => event.occurred_on && event.occurred_on === suggestion.event.occurred_on);
    return { mergeTarget: exact.length === 1 ? exact[0].event_id : "new" };
  }
  const current = data[suggestion.field];
  return { fieldChoice: current && current !== suggestion.value ? "keep" : "use" };
}

export function applyImportSuggestion(data, suggestion, decision = {}) {
  const ref = suggestion.reference;
  const existing = data.evidence.find((item) => item.document_id === ref.document_id && item.page_number === ref.page_number && item.start === ref.start && item.end === ref.end && item.page_text_sha256 === ref.page_text_sha256);
  if (!existing && data.evidence.length >= 15) throw new Error("Evidence limit reached. Remove a reference before importing more.");
  const evidence = existing ? data.evidence : [...data.evidence, ref];
  const next = { ...data, evidence, facts_confirmed: false, letter_text: "" };
  if (suggestion.event) {
    if (decision.mergeTarget && decision.mergeTarget !== "new") {
      const target = matchingImportEvents(data, suggestion).find((item) => item.event_id === decision.mergeTarget);
      if (!target) throw new Error("The selected event changed or has a conflicting date. Review the match again.");
      const ids = [...new Set([...target.evidence_ids, (existing || ref).evidence_id])];
      if (ids.length > 5) throw new Error("An event can link at most five excerpts.");
      next.events = data.events.map((item) => item.event_id === target.event_id
        ? { ...item, occurred_on: item.occurred_on || suggestion.event.occurred_on, evidence_ids: ids } : item);
      return next;
    }
    if (data.events.some((item) => item.kind === suggestion.event.kind && item.occurred_on === suggestion.event.occurred_on && item.description === suggestion.event.description && item.evidence_ids.includes((existing || ref).evidence_id))) throw new Error("This event is already in your timeline.");
    if (data.events.length >= 30) throw new Error("Timeline limit reached.");
    next.events = [...data.events, { ...suggestion.event, evidence_ids: [(existing || ref).evidence_id] }];
  } else {
    if (!["buyer_name", "seller_name", "seller_contact", "product", "order_reference", "amount_inr", "description", "requested_resolution"].includes(suggestion.field)) throw new Error("Unsupported suggestion.");
    const current = data[suggestion.field];
    const conflict = current && current !== suggestion.value;
    const choice = decision.fieldChoice || (conflict ? "keep" : "use");
    if (choice === "use") next[suggestion.field] = suggestion.value;
    else if (choice === "combine" && ["description", "requested_resolution"].includes(suggestion.field)) {
      if (typeof decision.combinedValue !== "string" || !decision.combinedValue.trim() || decision.combinedValue.length > 2000) throw new Error("Review the combined text (1-2,000 characters) before applying.");
      next[suggestion.field] = decision.combinedValue.trim();
    } else if (choice !== "keep") throw new Error("Choose how to handle this field.");
  }
  return next;
}

export function applyImportBatch(data, suggestions, decisions = {}) {
  const chosenFields = new Map();
  for (const item of suggestions) {
    if (!item.field) continue;
    const choice = decisions[item.suggestion_id] || importDecision(data, item);
    if (choice.fieldChoice === "keep") continue;
    const value = choice.fieldChoice === "combine" ? choice.combinedValue : item.value;
    if (chosenFields.has(item.field) && chosenFields.get(item.field) !== value) throw new Error("Choose just one replacement for each conflicting field.");
    chosenFields.set(item.field, value);
  }
  return suggestions.reduce((next, item) => applyImportSuggestion(next, item,
    decisions[item.suggestion_id] || importDecision(data, item)), data);
}

export function sourceSelection(text, start, end) {
  // DOM selections use UTF-16; the API/extracted page uses Unicode code points.
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end > text.length) return null;
  const splitsSurrogate = (position) => position > 0 && position < text.length
    && /[\uD800-\uDBFF]/.test(text[position - 1]) && /[\uDC00-\uDFFF]/.test(text[position]);
  if (splitsSurrogate(start) || splitsSurrogate(end)) return null;
  const first = Array.from(text.slice(0, start)).length;
  const last = Array.from(text.slice(0, end)).length;
  if (first >= last || last - first > 2000 || !text.slice(start, end).trim()) return null;
  return { start: first, end: last, quote: text.slice(start, end) };
}

export function complaintError(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Check the entered fields, valid dates and evidence references. Nothing was saved.";
  if (error?.response?.status === 429) return `Usage limit reached. Try again in ${error.response.headers?.["retry-after"] || "a few"} seconds.`;
  return "The complaint workspace is unavailable. Check your connection and retry. If a save timed out, refresh the case list before creating another copy.";
}

export function complaintPackHtml(pack, editedLetter = pack.draft_letter) {
  const h = escapeHtml;
  const references = new Map(pack.evidence.map((item, index) => [item.evidence_id, `E${index + 1}`]));
  const body = `<h1>Consumer Complaint Pack</h1><p>${h(pack.title)}</p><p>Preparation only - not submitted. Pack version ${h(pack.pack_version)}. Facts confirmed by user: ${pack.facts.facts_confirmed ? "yes" : "no"}.</p>
    <h2>Information and evidence checklist</h2><ul>${pack.checklist.map((item) => `<li>${item.complete ? "Recorded" : "Needs attention"}: ${h(item.label)}${item.required_for_draft ? " (needed for draft)" : " (supporting information, if available)"}</li>`).join("")}</ul>
    <h2>User-reported chronology</h2>${pack.timeline.length ? pack.timeline.map((event) => `<section><h3>${h(event.occurred_on || "Date not supplied")}</h3><p>${h(event.description)}</p><small>Linked by user: ${h(event.evidence_ids.map((id) => references.get(id) || "Unavailable reference").join(", ") || "No supporting excerpt linked")}</small></section>`).join("") : "<p>No chronology supplied.</p>"}
    <h2>Evidence index (excerpts, not original attachments)</h2>${pack.evidence.length ? pack.evidence.map((item, index) => `<section><h3>E${index + 1}: ${h(item.label)}</h3>${item.available ? `<p>${h(item.filename)} - page ${h(item.page_number)} - characters ${h(item.start)} to ${h(item.end)} (zero-based Unicode code points, end-exclusive)</p><pre>${h(item.quote)}</pre><small>Document: ${h(item.document_id)}<br>Page-text SHA-256: ${h(item.page_text_sha256)}</small>` : "<p>Source unavailable. No quote included. Remove or replace the reference.</p>"}</section>`).join("") : "<p>No supporting excerpts linked.</p>"}
    <h2>Editable complaint-letter draft</h2>${pack.draft_ready ? `<p>${pack.user_edited_draft || editedLetter !== pack.draft_letter ? "User-edited draft." : "Template draft from user-confirmed facts."} Review before sharing.</p><pre>${h(editedLetter)}</pre>` : "<p>No letter generated: complete the required facts and confirmation first.</p>"}
    <h2>Important limitations</h2><ul>${pack.notices.map((notice) => `<li>${h(notice)}</li>`).join("")}</ul><p>${h(pack.disclaimer)}</p><p>For manual grievance registration, visit the official National Consumer Helpline: https://consumerhelpline.gov.in/ . AskLaw does not submit this pack or operate that service.</p>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>Consumer Complaint Pack - AskLaw</title><style>body{max-width:900px;padding:24px;margin:auto;font:16px/1.65 system-ui;color:#192b40}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f8;padding:18px}p,small,li{overflow-wrap:anywhere}section{border-top:1px solid #ddd;padding:12px 0}small{font-size:12px}@media print{h2,h3{break-after:avoid}body{padding:0}}</style></head><body>${body}</body></html>`;
}
