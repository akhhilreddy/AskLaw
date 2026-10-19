import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../../services/api";
import { complaintError, importDecision, matchingImportEvents } from "../../services/complaintPack";
import { applyIntakeAnswer, applyNarrativeSuggestions, intakeQuestions } from "../../services/complaintIntake";
import ComplaintConfirmation from "./ComplaintConfirmation";

export default function ComplaintIntake({ data, disabled, onApply }) {
  const [description, setDescription] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState([]);
  const [reviewed, setReviewed] = useState(false);
  const [applied, setApplied] = useState(false);
  const [skipped, setSkipped] = useState([]);
  const [answer, setAnswer] = useState({ key: "", value: "" });
  const [error, setError] = useState("");
  const [eventChoices, setEventChoices] = useState({});
  const [replacement, setReplacement] = useState(null);
  const replacementSignature = JSON.stringify([data, selected, eventChoices]);
  const reviewSignature = JSON.stringify(data);
  const question = intakeQuestions(data, skipped)[0];
  const currentAnswer = answer.key === question?.key ? answer.value : "";

  async function prepare() {
    setBusy(true); setError(""); setResult(null); setApplied(false); setReviewed(false); setSkipped([]); setEventChoices({});
    try {
      const response = await api.post("/complaints/intake", { description, consent_to_ai: consent }, { timeout: 30000 });
      setResult(response.data);
      // Conflicting field candidates require an explicit choice, not last-write-wins.
      const counts = new Map();
      for (const item of response.data.suggestions) if (item.field) counts.set(item.field, (counts.get(item.field) || 0) + 1);
      setSelected(response.data.suggestions.filter((item) => !item.field || counts.get(item.field) === 1).map((item) => item.suggestion_id));
    } catch (requestError) { setError(complaintError(requestError)); }
    finally { setBusy(false); }
  }
  function apply(confirmed = false) {
    if (disabled || busy || reviewed !== reviewSignature || !selected.length) return;
    if (confirmed && replacement?.signature !== replacementSignature) return;
    const items = result.suggestions.filter((item) => selected.includes(item.suggestion_id));
    const overwrites = items.filter((item) => item.field && data[item.field] && data[item.field] !== item.value && !(item.field === "issue_type" && !data.description));
    if (overwrites.length && !confirmed) {
      setReplacement({ signature: replacementSignature, overwrites });
      return;
    }
    const matches = Object.fromEntries(items.filter((item) => item.event).map((item) => [item.suggestion_id, eventChoices[item.suggestion_id] || importDecision(data, item)]));
    try { onApply(applyNarrativeSuggestions(data, items, matches)); setApplied(true); setReplacement(null); setError(""); }
    catch (applyError) { setError(applyError.message); }
  }
  function respond() {
    try { onApply(applyIntakeAnswer(data, question, currentAnswer)); setAnswer({ key: "", value: "" }); setError(""); }
    catch (applyError) { setError(applyError.message); }
  }
  return <section className="complaint-card">
    <h2>Describe your problem</h2>
    <p>Tell us briefly what happened. We will suggest an unconfirmed account, then ask only for missing details. Defective products and refused refunds only.</p>
    <fieldset disabled={disabled || busy}>
      <legend>Your situation</legend>
      <label>Explain the consumer problem<textarea aria-label="Explain the consumer problem" maxLength={2000} value={description} onChange={(event) => { setDescription(event.target.value); setResult(null); setReviewed(false); setApplied(false); }} placeholder="Bought a laptop for INR 12k. It arrived broken and the seller refused a refund. I want my money back." /></label>
      <p>Avoid passwords, card numbers, Aadhaar details and unnecessary personal information. This text is sent to our existing Groq AI provider; PDFs are not sent by this step. Pending suggestions are not saved.</p>
      <label className="complaint-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I agree to send this description to the AI provider for suggested facts.</label>
      <button type="button" disabled={!consent || description.trim().length < 10} onClick={prepare}>{busy ? "Preparing suggestions…" : "Prepare my complaint"}</button>
    </fieldset>
    {busy && <p role="status">Reading your account. No facts are being saved or confirmed.</p>}
    {error && <p role="alert">{error}</p>}
    {result && !result.supported && <p role="status">No complaint guide for this situation yet. <Link to="/dashboard">Ask in normal research chat</Link>, or use the manual form below if your issue fits the supported categories.</p>}
    {result?.supported && !applied && <fieldset disabled={disabled || busy}>
      <legend>Review proposed facts - user-reported, not document evidence</legend>
      <p>Uncheck incorrect suggestions. An exact quote shows what you said, not that it is true. Check the issue category too. Missing dates stay unknown.</p>
      {result.suggestions.map((item) => <div className="complaint-event" key={item.suggestion_id}>
        <label className="complaint-check"><input type="checkbox" checked={selected.includes(item.suggestion_id)} onChange={(event) => { setSelected(event.target.checked ? [...selected, item.suggestion_id] : selected.filter((id) => id !== item.suggestion_id)); setReviewed(false); }} />{item.event ? `Timeline: ${item.event.kind} - ${item.event.occurred_on || "date unknown"}` : `${item.field.replaceAll("_", " ")}: ${item.value}`}</label>
        <blockquote>{item.quote}</blockquote>
        {item.event && <label>Timeline action<select aria-label={`Narrative timeline action for ${item.event.kind}`} value={(eventChoices[item.suggestion_id] || importDecision(data, item)).mergeTarget || "new"} onChange={(event) => { setEventChoices((current) => ({ ...current, [item.suggestion_id]: { mergeTarget: event.target.value } })); setReviewed(false); }}><option value="new">Add a separate event</option>{matchingImportEvents(data, item).map((event) => <option value={event.event_id} key={event.event_id}>Use existing {event.kind}: {event.occurred_on || "date unknown"} - {event.description.slice(0, 90)}</option>)}</select></label>}
        {item.field && data[item.field] && data[item.field] !== item.value && <p>Current value: {data[item.field]}</p>}
      </div>)}
      <label className="complaint-check"><input type="checkbox" checked={reviewed === reviewSignature} onChange={(event) => setReviewed(event.target.checked ? reviewSignature : false)} /> I reviewed the selected suggestions. Apply them as my unconfirmed account.</label>
      <button type="button" disabled={reviewed !== reviewSignature || !selected.length} onClick={() => apply()}>Apply reviewed suggestions</button>
      {replacement?.signature === replacementSignature && reviewed === reviewSignature && <ComplaintConfirmation title="Replace existing complaint values?" confirmLabel="Replace values and apply" onCancel={() => setReplacement(null)} onConfirm={() => apply(true)}>
        <p>Review each change below. Nothing is replaced until you confirm; applying does not save or confirm the facts.</p>
        {replacement.overwrites.map((item) => <div key={item.suggestion_id}><h4>{item.field.replaceAll("_", " ")}</h4><p><strong>Current:</strong> {data[item.field]}</p><p><strong>Suggested:</strong> {item.value}</p></div>)}
      </ComplaintConfirmation>}
    </fieldset>}
    {applied && <div><h3>Complete missing details</h3><p>PDF import below can fill missing details too. Conflicting document values require your review. You can edit everything in the form; no automatic save or filing.</p>
      {question ? <fieldset disabled={disabled || busy}><legend>One question at a time</legend><label>{question.prompt}<input aria-label="Answer missing detail" type={question.type || "text"} inputMode={question.field === "amount_inr" ? "decimal" : undefined} maxLength={question.maxLength} value={currentAnswer} onChange={(event) => setAnswer({ key: question.key, value: event.target.value })} /></label><button type="button" onClick={respond}>Use this answer</button>{" "}<button type="button" onClick={() => { setSkipped([...skipped, question.key]); setAnswer({ key: "", value: "" }); setError(""); }}>I don&apos;t know / skip</button></fieldset>
        : <p role="status">No more intake questions. Review the full facts, timeline and evidence below, confirm, then save and build. Skipped required details still block the letter.</p>}
    </div>}
  </section>;
}
