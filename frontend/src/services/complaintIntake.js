import { matchingImportEvents } from "./complaintPack.js";

const FIELDS = ["issue_type", "buyer_name", "seller_name", "seller_contact", "product", "order_reference", "amount_inr", "description", "requested_resolution"];

export function applyNarrativeSuggestions(data, suggestions, eventDecisions = {}) {
  const next = { ...data, events: [...data.events], facts_confirmed: false, letter_text: "" };
  const values = new Map();
  for (const item of suggestions) {
    if (item.origin !== "user_report" || item.reference) throw new Error("Invalid narrative suggestion.");
    if (item.event) {
      const event = { ...item.event, evidence_ids: [] };
      const targetId = eventDecisions[item.suggestion_id]?.mergeTarget;
      if (targetId && targetId !== "new") {
        const target = matchingImportEvents(data, item).find((old) => old.event_id === targetId);
        if (!target) throw new Error("The selected timeline match changed or has a conflicting date. Review it again.");
        next.events = next.events.map((old) => old.event_id === targetId
          ? { ...old, occurred_on: old.occurred_on || event.occurred_on } : old);
        continue;
      }
      if (!next.events.some((old) => old.kind === event.kind && old.occurred_on === event.occurred_on && old.description === event.description)) next.events.push(event);
      if (next.events.length > 30) throw new Error("Timeline limit reached. Remove an event first.");
    } else {
      if (!FIELDS.includes(item.field)) throw new Error("Unsupported suggestion.");
      if (values.has(item.field) && values.get(item.field) !== item.value) throw new Error("Select only one value for each conflicting field.");
      values.set(item.field, item.value);
      next[item.field] = item.value;
    }
  }
  return next;
}

export function intakeQuestions(data, skipped = []) {
  const prompts = [
    ["buyer_name", "What name should appear on your complaint?", 200],
    ["seller_name", "Which seller or company is this about?", 200],
    ["seller_contact", "What seller email or address can you use?", 200],
    ["product", "What product did you purchase?", 200],
    ["description", "What happened? Describe the problem in your own words.", 2000],
    ["requested_resolution", "What do you want the seller to do: refund, replacement, repair, or something else?", 2000],
    ["amount_inr", "What was the transaction amount in INR? Leave it unknown if you are unsure.", 13],
  ].filter(([key]) => !data[key]?.trim()).map(([key, prompt, maxLength]) => ({ key, field: key, prompt, maxLength }));
  for (const event of data.events) {
    if (!event.occurred_on) prompts.push({ key: `date-${event.event_id}`, eventId: event.event_id, prompt: `What was the date of this ${event.kind} event? ${event.description}`, type: "date" });
  }
  return prompts.filter((item) => !skipped.includes(item.key));
}

export function applyIntakeAnswer(data, question, answer) {
  const value = answer.trim();
  if (!value) throw new Error("Enter an answer or choose ‘I don't know / skip’.");
  if (question.eventId) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) throw new Error("Enter a valid date or leave it unknown.");
    return { events: data.events.map((event) => event.event_id === question.eventId ? { ...event, occurred_on: value } : event) };
  }
  if (!FIELDS.includes(question.field) || value.length > question.maxLength) throw new Error("Check this answer's length.");
  if (question.field === "amount_inr" && !/^\d{1,10}(?:\.\d{1,2})?$/.test(value)) throw new Error("Enter an INR amount without commas, for example 12000.00.");
  return { [question.field]: value };
}
