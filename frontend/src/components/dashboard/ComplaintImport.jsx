import { useState } from "react";
import api from "../../services/api";
import { applyImportBatch, complaintError, importDecision, matchingImportEvents } from "../../services/complaintPack";

export default function ComplaintImport({ documents, disabled, data, onApply }) {
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [accepted, setAccepted] = useState([]);
  const [included, setIncluded] = useState([]);
  const [decisions, setDecisions] = useState({});
  const [reviewed, setReviewed] = useState({});
  const reviewSignature = JSON.stringify(data);

  async function extract() {
    setBusy(true); setError(""); setResult(null); setAccepted([]); setReviewed({}); setDecisions({});
    try {
      const response = await api.post("/complaints/import", { document_ids: selected }, { timeout: 15000 });
      setResult(response.data);
      setIncluded(response.data.suggestions.map((item) => item.suggestion_id));
    } catch (requestError) { setError(complaintError(requestError)); }
    finally { setBusy(false); }
  }

  function decide(item, patch) {
    setDecisions((current) => ({ ...current, [item.suggestion_id]: { ...(current[item.suggestion_id] || importDecision(data, item)), ...patch } }));
    setReviewed((values) => ({ ...values, [item.reference.document_id]: null }));
  }

  function apply(documentId) {
    if (reviewed[documentId] !== reviewSignature) return;
    const items = result.suggestions.filter((item) => item.reference.document_id === documentId && included.includes(item.suggestion_id) && !accepted.includes(item.suggestion_id));
    try {
      onApply(applyImportBatch(data, items, decisions));
      setAccepted((ids) => [...ids, ...items.map((item) => item.suggestion_id)]);
      setReviewed((values) => ({ ...values, [documentId]: null })); setError("");
    } catch (applyError) { setError(applyError.message); }
  }

  const groups = result ? [...new Map(result.suggestions.map((item) => [item.reference.document_id, item.filename])).entries()] : [];
  return <section className="complaint-card complaint-import">
    <h2>Start from your PDFs</h2>
    <p>Select up to two indexed documents. Review suggestions together per document. Existing text is kept by default; matching events can receive source links instead of duplicate entries. Matches are suggestions, not proof.</p>
    <fieldset disabled={disabled || busy}>
      <legend>Records to review</legend>
      {documents.filter((item) => !item.unavailable_reason).map((item) => <label className="complaint-check" key={item.document_id}><input type="checkbox" checked={selected.includes(item.document_id)} disabled={!selected.includes(item.document_id) && selected.length >= 2} onChange={(event) => { setSelected(event.target.checked ? [...selected, item.document_id] : selected.filter((id) => id !== item.document_id)); setResult(null); }} />{item.filename}</label>)}
      <button type="button" disabled={!selected.length} onClick={extract}>{busy ? "Reading records…" : "Suggest fields & timeline"}</button>
    </fieldset>
    {busy && <p role="status">Reading your selected records…</p>}
    {error && <p role="alert">{error}</p>}
    {result && <div><p role="status">{result.suggestions.length} suggestions. Nothing is saved or confirmed by import. Unknown layouts and dates still require manual entry.</p>{result.truncated && <p>Suggestion limit reached. Review remaining pages manually.</p>}
      {groups.map(([documentId, filename]) => {
        const items = result.suggestions.filter((item) => item.reference.document_id === documentId);
        const pending = items.filter((item) => included.includes(item.suggestion_id) && !accepted.includes(item.suggestion_id));
        return <fieldset key={documentId} disabled={disabled || busy} className="complaint-event"><legend>Review document: {filename}</legend>
          {items.map((item) => {
            const decision = decisions[item.suggestion_id] || importDecision(data, item);
            const current = item.field ? data[item.field] : null;
            const conflict = current && current !== item.value;
            const applied = accepted.includes(item.suggestion_id);
            return <div className="complaint-import-row" key={item.suggestion_id}>
              <label className="complaint-check"><input type="checkbox" disabled={applied} checked={included.includes(item.suggestion_id)} onChange={(event) => { setIncluded(event.target.checked ? [...included, item.suggestion_id] : included.filter((id) => id !== item.suggestion_id)); setReviewed((values) => ({ ...values, [documentId]: null })); }} />{item.event ? `${item.event.kind} - ${item.event.occurred_on || "date unknown"}` : `${item.field.replaceAll("_", " ")}: ${item.value}`}{applied ? " (applied)" : ""}</label>
              <details><summary>View exact source excerpt - page {item.reference.page_number}</summary><blockquote>{item.quote}</blockquote></details>
              {!applied && item.event && <label>Timeline action<select aria-label={`Timeline action for ${item.event.kind} in ${filename}`} value={decision.mergeTarget || "new"} onChange={(event) => decide(item, { mergeTarget: event.target.value })}><option value="new">Add a separate event</option>{matchingImportEvents(data, item).map((event) => <option value={event.event_id} key={event.event_id}>Attach source to existing {event.kind}: {event.occurred_on || "date unknown"} - {event.description.slice(0, 90)}</option>)}</select></label>}
              {!applied && conflict && <><p>Current value (kept unless you choose otherwise): {current}</p><label>How should this field be handled?<select aria-label={`Handle ${item.field} in ${filename}`} value={decision.fieldChoice || "keep"} onChange={(event) => decide(item, { fieldChoice: event.target.value, combinedValue: decision.combinedValue ?? `${current}\n\nAdditional record excerpt:\n${item.value}` })}><option value="keep">Keep mine; add source reference only</option><option value="use">Use the document value</option>{["description", "requested_resolution"].includes(item.field) && <option value="combine">Combine and edit before applying</option>}</select></label>{decision.fieldChoice === "combine" && <label>Review combined text<textarea aria-label={`Combined ${item.field}`} maxLength={2000} value={decision.combinedValue || ""} onChange={(event) => decide(item, { combinedValue: event.target.value })} /></label>}</>}
            </div>;
          })}
          <label className="complaint-check"><input type="checkbox" checked={reviewed[documentId] === reviewSignature} onChange={(event) => setReviewed((values) => ({ ...values, [documentId]: event.target.checked ? reviewSignature : null }))} />I reviewed the selected fields, text choices and timeline matches for this document.</label>
          <button type="button" disabled={reviewed[documentId] !== reviewSignature || !pending.length} onClick={() => apply(documentId)}>Apply reviewed document</button>
        </fieldset>;
      })}
    </div>}
  </section>;
}
