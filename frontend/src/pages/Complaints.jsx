import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download, FolderOpen, Plus, Save } from "lucide-react";
import AppLayout from "../layout/AppLayout";
import ComplaintEvidencePicker from "../components/dashboard/ComplaintEvidencePicker";
import ComplaintImport from "../components/dashboard/ComplaintImport";
import ComplaintIntake from "../components/dashboard/ComplaintIntake";
import ComplaintConfirmation from "../components/dashboard/ComplaintConfirmation";
import { getMe } from "../services/authService";
import api from "../services/api";
import { complaintError, complaintPackHtml, emptyComplaint } from "../services/complaintPack";
import "../styles/complaints.css";

const fields = [["buyer_name", "Your name"], ["seller_name", "Seller / company"], ["seller_contact", "Seller contact / address"], ["product", "Product"], ["order_reference", "Order / reference number (optional)"], ["amount_inr", "Transaction amount in INR (optional)"]];

export default function Complaints() {
  const [user, setUser] = useState(null);
  const [cases, setCases] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [data, setData] = useState(emptyComplaint);
  const [saved, setSaved] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [pack, setPack] = useState(null);
  const [letter, setLetter] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [intakeSession, setIntakeSession] = useState(0);
  const [confirmation, setConfirmation] = useState(null);
  const confirmationSignature = JSON.stringify([data, saved, dirty, letter]);
  const pendingConfirmation = confirmation?.signature === confirmationSignature ? confirmation : null;

  function requestConfirmation(kind, caseId) {
    setConfirmation({ kind, caseId, signature: confirmationSignature });
  }
  function confirmPending() {
    if (!pendingConfirmation || busy) return;
    setConfirmation(null);
    if (pendingConfirmation.kind === "new") newComplaint(true);
    else if (pendingConfirmation.kind === "open") openCase(pendingConfirmation.caseId, true);
    else removeCase(true);
  }

  useEffect(() => {
    let active = true;
    getMe().then(async (current) => {
      if (active) setUser(current);
      if (current.is_guest) return;
      const [caseResponse, documentResponse] = await Promise.all([api.get("/complaints", { timeout: 10000 }), api.get("/complaints/documents", { timeout: 10000 })]);
      if (active) { setCases(caseResponse.data); setDocuments(documentResponse.data); }
    }).catch((requestError) => { if (active) setError(complaintError(requestError)); })
      .finally(() => { if (active) { setLoading(false); setRefreshing(false); } });
    return () => { active = false; };
  }, [retry]);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function edit(patch, facts = true) {
    setData((current) => ({ ...current, ...patch, ...(facts ? { facts_confirmed: false, letter_text: "" } : {}) }));
    setDirty(true); setPack(null); setReviewed(false);
  }

  async function refreshCases() { setCases((await api.get("/complaints", { timeout: 10000 })).data); }

  function newComplaint(confirmed = false) {
    if (busy) return;
    if (dirty && confirmed !== true) { requestConfirmation("new"); return; }
    setSaved(null); setData(emptyComplaint()); setDirty(false); setPack(null); setReviewed(false);
    setIntakeSession((value) => value + 1);
  }

  async function save(next = data) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = saved
        ? await api.put(`/complaints/${saved.case_id}`, { revision: saved.revision, data: next }, { timeout: 20000 })
        : await api.post("/complaints", next, { timeout: 20000 });
      setSaved(response.data); setData(response.data.data); setDirty(false); setPack(null); setReviewed(false);
      // A list refresh failure must not make a successful save look failed.
      try { await refreshCases(); } catch { /* Saved ID/revision remain visible. */ }
    } catch (requestError) { setError(complaintError(requestError)); }
    finally { setBusy(false); }
  }

  async function openCase(caseId, confirmed = false) {
    if (busy) return;
    if (dirty && confirmed !== true) { requestConfirmation("open", caseId); return; }
    setBusy(true); setError("");
    try {
      const response = await api.get(`/complaints/${caseId}`, { timeout: 10000 });
      setSaved(response.data); setData(response.data.data); setDirty(false); setPack(null); setReviewed(false);
      setIntakeSession((value) => value + 1);
    } catch (requestError) { setError(complaintError(requestError)); }
    finally { setBusy(false); }
  }

  async function build() {
    if (busy || dirty || !saved) return;
    setBusy(true); setError(""); setPack(null); setReviewed(false);
    try {
      const response = await api.post(`/complaints/${saved.case_id}/pack`, { revision: saved.revision }, { timeout: 15000 });
      setPack(response.data); setLetter(response.data.draft_letter || "");
    } catch (requestError) { setError(complaintError(requestError)); }
    finally { setBusy(false); }
  }

  async function removeCase(confirmed = false) {
    if (!saved || busy) return;
    if (confirmed !== true) { requestConfirmation("delete"); return; }
    setBusy(true); setError("");
    try {
      await api.delete(`/complaints/${saved.case_id}`, { params: { revision: saved.revision }, timeout: 10000 });
      setSaved(null); setData(emptyComplaint()); setPack(null); setDirty(false); setReviewed(false);
      setIntakeSession((value) => value + 1);
      try { await refreshCases(); } catch { /* Explicit refresh remains available. */ }
    } catch (requestError) { setError(complaintError(requestError)); }
    finally { setBusy(false); }
  }

  function download() {
    if (!pack || !reviewed) return;
    const url = URL.createObjectURL(new Blob([complaintPackHtml(pack, letter)], { type: "text/html;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "asklaw-consumer-complaint-pack.html";
    document.body.append(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const evidenceLabels = new Map(data.evidence.map((item, index) => [item.evidence_id, `E${index + 1}: ${item.label}`]));
  return <AppLayout userName={user?.name || "Account"}><div className="complaints-page">
    <header><span className="eyebrow">From scattered records to an organized complaint</span><h1>Consumer Complaint Pack<span>.</span></h1><p>Prepare your facts, chronology and supporting excerpts. Review an editable letter before sharing anything.</p></header>
    <aside className="complaint-warning">AskLaw provides legal information, not legal advice. Nothing here files a grievance, proves your claim or guarantees a refund. First release: defective products and refused refunds; text-based PDFs only.</aside>
    {error && <p className="complaint-error" role="alert">{error}</p>}
    {loading ? <p role="status">Loading your workspace…</p> : user?.is_guest ? <section className="complaint-card"><h2>Keep private complaint records in your own account.</h2><p><Link to="/signup">Create an account</Link> or <Link to="/login">sign in</Link> to save complaints and link your uploaded PDFs. Guest access remains web research only.</p></section> : user && <>
      <section className="complaint-card complaint-library"><div><h2>Saved complaints</h2><p>Latest 50. Save edits before leaving this page.</p></div><button type="button" disabled={busy} onClick={newComplaint}><Plus size={15} /> New complaint</button><button type="button" disabled={busy || refreshing} onClick={() => { setRefreshing(true); setError(""); setRetry((value) => value + 1); }}>{refreshing ? "Refreshing lists…" : "Refresh lists"}</button><div className="complaint-case-list">{cases.length ? cases.map((item) => <button type="button" key={item.case_id} disabled={busy} aria-pressed={saved?.case_id === item.case_id} onClick={() => openCase(item.case_id)}><FolderOpen size={14} /> {item.title}</button>) : <p>No saved complaints yet.</p>}</div></section>
      {pendingConfirmation && <ComplaintConfirmation key={`${pendingConfirmation.kind}-${pendingConfirmation.caseId || ""}`} title={pendingConfirmation.kind === "delete" ? "Delete this complaint?" : "Discard unsaved edits?"} confirmLabel={pendingConfirmation.kind === "delete" ? "Delete saved complaint" : pendingConfirmation.kind === "open" ? "Discard edits and open complaint" : "Discard edits and start new"} disabled={busy} onCancel={() => setConfirmation(null)} onConfirm={confirmPending}>
        <p>{pendingConfirmation.kind === "delete" ? "This removes the complaint and its saved draft. Your uploaded PDFs will be kept." : pendingConfirmation.kind === "open" ? "Your unsaved edits will be discarded before opening the selected complaint." : "Your unsaved edits will be discarded before starting a new complaint."}</p>
      </ComplaintConfirmation>}
      <ComplaintIntake key={`intake-${intakeSession}`} data={data} disabled={busy} onApply={(patch) => edit(patch)} />
      <ComplaintImport key={`import-${intakeSession}`} documents={documents} disabled={busy} data={data} onApply={(patch) => edit(patch)} />
      <form onSubmit={(event) => { event.preventDefault(); save(); }}>
        <fieldset disabled={busy} className="complaint-card"><legend>1 / Your account of what happened</legend><div className="complaint-grid"><label>Workspace title<input required maxLength={120} value={data.title} onChange={(event) => edit({ title: event.target.value })} /></label><label>Issue type<select value={data.issue_type} onChange={(event) => edit({ issue_type: event.target.value })}><option value="defective_product">Defective product</option><option value="refused_refund">Refused refund</option></select></label>{fields.map(([key, label]) => <label key={key}>{label}<input maxLength={key === "amount_inr" ? 13 : 200} inputMode={key === "amount_inr" ? "decimal" : "text"} placeholder={key === "amount_inr" ? "Example: 12000.00 (no commas)" : ""} value={data[key]} onChange={(event) => edit({ [key]: event.target.value })} /></label>)}</div><label>What went wrong?<textarea maxLength={2000} value={data.description} onChange={(event) => edit({ description: event.target.value })} /></label><label>Resolution you request<textarea maxLength={2000} value={data.requested_resolution} onChange={(event) => edit({ requested_resolution: event.target.value })} placeholder="State the resolution you want, without guessing legal entitlements." /></label></fieldset>
        <fieldset disabled={busy} className="complaint-card"><legend>2 / Timeline you can confirm</legend><p>Use actual dates; leave unknown dates blank. Source links are your assertions, not an automated finding that a source supports an event.</p>{data.events.map((event, index) => <div className="complaint-event" key={event.event_id}><div className="complaint-grid"><label>Event {index + 1}<select value={event.kind} onChange={(change) => edit({ events: data.events.map((item, i) => i === index ? { ...item, kind: change.target.value } : item) })}>{["purchase", "delivery", "problem", "contact", "response", "other"].map((kind) => <option key={kind}>{kind}</option>)}</select></label><label>Date (optional)<input type="date" value={event.occurred_on || ""} onChange={(change) => edit({ events: data.events.map((item, i) => i === index ? { ...item, occurred_on: change.target.value || null } : item) })} /></label></div><label>Description<textarea required maxLength={1000} value={event.description} onChange={(change) => edit({ events: data.events.map((item, i) => i === index ? { ...item, description: change.target.value } : item) })} /></label>{data.evidence.length > 0 && <label>Supporting excerpts (multiple selection)<select multiple value={event.evidence_ids} onChange={(change) => edit({ events: data.events.map((item, i) => i === index ? { ...item, evidence_ids: Array.from(change.target.selectedOptions, (option) => option.value) } : item) })}>{data.evidence.map((item) => <option key={item.evidence_id} value={item.evidence_id}>{evidenceLabels.get(item.evidence_id)}</option>)}</select></label>}<button type="button" onClick={() => edit({ events: data.events.filter((_, i) => i !== index) })}>Remove event</button></div>)}<button type="button" disabled={data.events.length >= 30} onClick={() => edit({ events: [...data.events, { event_id: `t-${crypto.randomUUID()}`, kind: "other", occurred_on: null, description: "", evidence_ids: [] }] })}><Plus size={15} /> Add timeline event</button></fieldset>
        <fieldset disabled={busy} className="complaint-card"><legend>3 / Evidence index</legend><p><Link to="/documents">Upload records in Documents</Link>, wait for Indexed, then refresh the lists here. Older uploads without complete page text need re-uploading. Scans/images and original-file bundling are not supported.</p>{data.evidence.map((item, index) => <div className="complaint-evidence-row" key={item.evidence_id}><span>E{index + 1}: {item.label} - page {item.page_number}</span><button type="button" onClick={() => edit({ evidence: data.evidence.filter((ref) => ref.evidence_id !== item.evidence_id), events: data.events.map((event) => ({ ...event, evidence_ids: event.evidence_ids.filter((id) => id !== item.evidence_id) })) })}>Remove reference</button></div>)}<ComplaintEvidencePicker documents={documents} disabled={busy || data.evidence.length >= 15} onAdd={(reference) => edit({ evidence: [...data.evidence, reference] })} /></fieldset>
        <section className="complaint-card"><label className="complaint-check"><input type="checkbox" disabled={busy} checked={data.facts_confirmed} onChange={(event) => edit({ facts_confirmed: event.target.checked }, false)} /> I checked the names, amounts, dates, descriptions and evidence links. These are my account of events.</label><div className="complaint-actions"><button className="primary-button" type="submit" disabled={busy}><Save size={16} /> {busy ? "Working…" : "Save complaint"}</button><button type="button" disabled={busy || dirty || !saved} onClick={build}>Build checklist & draft</button>{saved && <button type="button" disabled={busy} onClick={removeCase}>Delete complaint</button>}</div><p role="status">{dirty ? "Unsaved changes - save before building or leaving." : saved ? `Saved revision ${saved.revision}. You can resume it from Saved complaints.` : "Not saved yet. Partial facts can be saved; confirmation is needed for a letter."}</p></section>
      </form>
      {pack && <section className="complaint-card complaint-pack"><span className="eyebrow">Preparation, not submission</span><h2>Your complaint pack</h2><h3>Missing-information checklist</h3><ul>{pack.checklist.map((item) => <li key={item.key}>{item.complete ? "Recorded" : "Needs attention"}: {item.label}</li>)}</ul><h3>User-reported timeline</h3>{pack.timeline.length ? <ol>{pack.timeline.map((event) => <li key={event.event_id}><strong>{event.occurred_on || "Date not supplied"}</strong> - {event.description}<p className="complaint-muted">Linked: {event.evidence_ids.map((id) => evidenceLabels.get(id)).join(", ") || "No excerpt linked"}</p></li>)}</ol> : <p>No chronology supplied.</p>}<h3>Source-checked excerpts</h3>{pack.evidence.map((item, index) => <div key={item.evidence_id}><h4>E{index + 1}: {item.label}</h4>{item.available ? <><blockquote>{item.quote}</blockquote><details><summary>Source reference</summary><small>{item.filename} - page {item.page_number}; characters {item.start}-{item.end}; document {item.document_id}<br />Page-text SHA-256: {item.page_text_sha256}</small></details></> : <p role="status">Source unavailable. No quote included; remove or replace this reference.</p>}</div>)}<h3>Complaint letter - review and edit</h3>{pack.draft_ready ? <><textarea className="complaint-letter" aria-label="Editable complaint letter" value={letter} maxLength={16000} onChange={(event) => { setLetter(event.target.value); setReviewed(false); }} /><button type="button" disabled={busy} onClick={() => save({ ...data, letter_text: letter })}>Save edited letter (then build again)</button></> : <p>Complete the required facts and confirmation, save, then build again to create a letter.</p>}<ul className="complaint-muted">{pack.notices.map((notice) => <li key={notice}>{notice}</li>)}</ul><label className="complaint-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /> I reviewed this pack and any edited letter before downloading.</label><button className="primary-button" type="button" disabled={!reviewed} onClick={download}><Download size={16} /> Download HTML pack</button><p className="complaint-muted">Open the downloaded file in a browser and Print → Save as PDF. Original PDF files are not attached.</p><p>{pack.disclaimer}</p><a href="https://consumerhelpline.gov.in/" target="_blank" rel="noreferrer">Official National Consumer Helpline (manual submission)</a></section>}
    </>}
  </div></AppLayout>;
}
