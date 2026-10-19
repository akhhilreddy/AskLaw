import { useEffect, useRef, useState } from "react";
import { ArrowRight, Download, FileDiff, FileSearch, FlaskConical, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import AppLayout from "../layout/AppLayout";
import api from "../services/api";
import { getMe } from "../services/authService";
import { agreementError, agreementReportHtml, changeLabels, termLabels } from "../services/agreementReport";
import "../styles/agreements.css";

function SourceQuote({ source, title }) {
  const label = source.scope === "clause_candidate" ? "Clause candidate" : source.scope === "context_excerpt" ? "Local context excerpt" : "Source passage";
  return <figure className="agreement-quote">
    <figcaption>{title || label} · page {source.page_number}{source.is_partial ? " · clipped excerpt" : ""}</figcaption>
    <blockquote>{source.quote}</blockquote>
    <details><summary>Source reference</summary><small>Document {source.document_id}<br />Characters {source.start}–{source.end} (zero-based, end exclusive)<br />Page-text SHA-256: {source.page_text_sha256}</small></details>
  </figure>;
}

export default function Agreements() {
  const [user, setUser] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState("compare");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [result, setResult] = useState(null);
  const [sample, setSample] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  const resultRef = useRef(null);

  useEffect(() => {
    let active = true;
    getMe().then(async (current) => {
      const items = current.is_guest ? [] : (await api.get("/agreements/documents", { timeout: 15000 })).data;
      if (active) { setUser(current); setDocuments(items); }
    }).catch((requestError) => { if (active) setError(agreementError(requestError)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; generation.current += 1; };
  }, [reload]);

  async function run(useSample = false) {
    if (busy) return;
    const request = ++generation.current;
    setBusy(true); setError(""); setResult(null);
    try {
      let report;
      if (useSample) {
        const response = await api.get("/agreements/demo", { timeout: 15000 });
        report = mode === "compare" ? response.data.comparison : response.data.review;
      } else {
        const response = mode === "compare"
          ? await api.post("/agreements/compare", { before_id: before, after_id: after }, { timeout: 20000 })
          : await api.post("/agreements/review", { document_id: before }, { timeout: 20000 });
        report = response.data;
      }
      if (generation.current === request) {
        setSample(useSample); setResult(report);
        window.requestAnimationFrame(() => resultRef.current?.focus());
      }
    } catch (requestError) {
      if (generation.current === request) setError(agreementError(requestError));
    } finally {
      if (generation.current === request) setBusy(false);
    }
  }

  function changeSelection(action) {
    action(); setResult(null); setError("");
  }

  function download() {
    const url = URL.createObjectURL(new Blob([agreementReportHtml(result, sample)], { type: "text/html;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = `asklaw-${sample ? "sample-" : ""}${mode}-report.html`;
    document.body.append(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const canRun = before && (mode !== "compare" || (after && before !== after));
  const options = documents.map((item) => <option key={item.document_id} value={item.document_id} disabled={Boolean(item.unavailable_reason)}>{item.filename}{item.unavailable_reason ? " — not ready for review" : ""}</option>);

  return <AppLayout userName={user?.name || "Account"}>
    <div className="agreements-page">
      <header className="agreement-heading"><span className="eyebrow">A closer look at your documents</span><h1>Before You Sign<span>.</span></h1><p>Find key-term mentions. Compare two versions. Keep the exact passages behind every change.</p></header>
      <aside className="agreement-disclaimer">AskLaw provides legal information, not legal advice. This text-only tool does not decide whether a term is lawful, enforceable or safe to sign.</aside>
      <div className="agreement-tabs" aria-label="Review tools">
        <button type="button" disabled={busy} aria-pressed={mode === "compare"} onClick={() => changeSelection(() => setMode("compare"))}><FileDiff size={18} /> Compare versions</button>
        <button type="button" disabled={busy} aria-pressed={mode === "review"} onClick={() => changeSelection(() => setMode("review"))}><FileSearch size={18} /> Find key terms</button>
      </div>
      <section className="agreement-panel" aria-label="Select agreements" aria-busy={busy || loading}>
        <div className="agreement-panel-heading"><h2>{mode === "compare" ? "What changed between versions?" : "What does the agreement mention?"}</h2><span>English · text-based rental agreements</span></div>
        <p>Upload PDFs in Documents first. Every page must contain readable text. Up to 50 pages and 100,000 extracted characters per agreement.</p>
        {loading ? <p role="status">Loading your document library…</p> : user?.is_guest ? <p>Guest access can try the synthetic sample. <Link to="/signup">Create an account</Link> to upload and review your own agreements.</p> : <>
          <form onSubmit={(event) => { event.preventDefault(); run(); }}>
            <div className="agreement-selectors"><label>{mode === "compare" ? "Original version" : "Agreement"}<select disabled={busy || !documents.length} value={before} onChange={(event) => changeSelection(() => setBefore(event.target.value))}><option value="">Select a document</option>{options}</select></label>
              {mode === "compare" && <label>Revised version<select disabled={busy || !documents.length} value={after} onChange={(event) => changeSelection(() => setAfter(event.target.value))}><option value="">Select a different document</option>{options}</select></label>}</div>
            {before && before === after && mode === "compare" && <p>Select two different uploads to compare versions.</p>}
            <div className="agreement-actions"><button className="primary-button" type="submit" disabled={busy || !canRun}>{busy ? "Preparing report…" : mode === "compare" ? "Compare exact text" : "Find key-term mentions"}<ArrowRight size={16} /></button><Link to="/documents">Upload an agreement</Link></div>
          </form>
          {!documents.length && <p>No uploads yet. Try the sample below, or upload a text-based agreement.</p>}
          {documents.some((item) => item.unavailable_reason) && <details className="agreement-unsupported"><summary>Why are some documents unavailable?</summary><ul>{documents.filter((item) => item.unavailable_reason).map((item) => <li key={item.document_id}><strong>{item.filename}:</strong> {item.unavailable_reason}</li>)}</ul></details>}
          <button className="agreement-text-button" disabled={busy} type="button" onClick={() => { setLoading(true); setError(""); setReload((value) => value + 1); }}><RefreshCw size={14} /> Refresh library (latest 100 uploads)</button>
        </>}
        <div className="agreement-sample"><FlaskConical size={20} /><div><strong>See it with a sample</strong><p>A fictional deposit changes from INR 10,000 to INR 15,000, and notice from 30 to 90 days. Not a legal template.</p></div><button type="button" disabled={busy} onClick={() => run(true)}>{busy ? "Preparing…" : "Try sample"}</button></div>
      </section>
      {error && <p className="agreement-error" role="alert">{error}</p>}
      {busy && <p role="status">Comparing extracted text and attaching exact page references…</p>}
      {result && <section className="agreement-results" ref={resultRef} tabIndex={-1} aria-label="Agreement report">
        <div className="agreement-result-heading"><div><span className="eyebrow">{sample ? "Synthetic sample report" : "Your document report"}</span><h2>{mode === "compare" ? "The changes, in context." : "Key-term mentions."}</h2></div><button type="button" onClick={download}><Download size={16} /> Download report</button></div>
        <p className="agreement-report-note">HTML report · open in a browser, then Print → Save as PDF. Generated on demand; no separate report history is stored.</p>
        {mode === "compare" ? <>
          <p><strong>Original:</strong> {result.before.title}<br /><strong>Revised:</strong> {result.after.title}</p>
          <div className="agreement-summary">{Object.entries(result.summary).map(([kind, count]) => <div key={kind}><strong>{count}</strong><span>{changeLabels[kind]} groups</span></div>)}</div>
          {!result.changes.length && <p>No extracted-text differences found. This does not prove the signed PDFs are identical.</p>}
          {result.changes.map((change, index) => <article className={`agreement-change agreement-change-${change.kind}`} key={index}><h3>{String(index + 1).padStart(2, "0")} / {changeLabels[change.kind]}</h3><div className="agreement-comparison"><div><h4>Original</h4>{change.before.length ? change.before.map((source, i) => <SourceQuote key={i} source={source} />) : <p>No original passage.</p>}</div><div><h4>Revised</h4>{change.after.length ? change.after.map((source, i) => <SourceQuote key={i} source={source} />) : <p>No revised passage.</p>}</div></div>{(change.numeric_tokens_before.length || change.numeric_tokens_after.length) > 0 && <p className="agreement-report-note">Literal amount / period tokens: {change.numeric_tokens_before.join(" · ") || "none"} → {change.numeric_tokens_after.join(" · ") || "none"}. Quoted observations, not calculated obligations.</p>}</article>)}
        </> : <><h3>{result.title}</h3>{result.terms.map((term) => <article className="agreement-term" key={term.kind}><h3>{termLabels[term.kind]}</h3>{term.mentions.length ? <><p>Candidate mentions — read the full agreement for context.</p>{term.mentions.map((source, index) => <SourceQuote key={index} source={source} />)}</> : <p>Not identified by keyword matching. This does not mean the term is absent.</p>}</article>)}</>}
        <aside className="agreement-limitations"><h3>What this report cannot tell you</h3><ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p>{result.disclaimer}</p><p>Have a qualified lawyer review consequential or unclear terms before signing.</p></aside>
      </section>}
    </div>
  </AppLayout>;
}
