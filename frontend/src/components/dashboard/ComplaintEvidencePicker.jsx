import { useEffect, useState } from "react";
import api from "../../services/api";
import { complaintError, sourceSelection } from "../../services/complaintPack";

export default function ComplaintEvidencePicker({ documents, disabled, onAdd }) {
  const [documentId, setDocumentId] = useState("");
  const [pageNumber, setPageNumber] = useState(1);
  const [page, setPage] = useState(null);
  const [selection, setSelection] = useState(null);
  const [label, setLabel] = useState("");
  const [category, setCategory] = useState("invoice");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const selectedDocument = documents.find((item) => item.document_id === documentId);

  useEffect(() => {
    if (!documentId) return undefined;
    const controller = new AbortController();
    api.get(`/complaints/documents/${documentId}/pages/${pageNumber}`, { signal: controller.signal, timeout: 10000 })
      .then((response) => { if (!controller.signal.aborted) setPage(response.data); })
      .catch((requestError) => { if (!controller.signal.aborted) setError(complaintError(requestError)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [documentId, pageNumber]);

  function resetPage() { setPage(null); setSelection(null); setError(""); setLoading(true); }

  return <div className="complaint-evidence-picker">
    <h3>Link an exact PDF excerpt</h3><p>Select an owned indexed PDF, then highlight 1-2,000 characters in its extracted text. This checks text location, not whether it proves your claim.</p>
    <div className="complaint-grid"><label>Source document<select value={documentId} disabled={disabled} onChange={(event) => { resetPage(); setDocumentId(event.target.value); setPageNumber(1); if (!event.target.value) setLoading(false); }}><option value="">Select a PDF</option>{documents.map((item) => <option key={item.document_id} value={item.document_id} disabled={Boolean(item.unavailable_reason)}>{item.filename}{item.unavailable_reason ? " (not available)" : ""}</option>)}</select></label>
    {selectedDocument && <label>Page<select value={pageNumber} disabled={disabled} onChange={(event) => { resetPage(); setPageNumber(Number(event.target.value)); }}>{Array.from({ length: selectedDocument.page_count || 1 }, (_, index) => <option key={index} value={index + 1}>{index + 1}</option>)}</select></label>}</div>
    {loading && <p role="status">Loading source page…</p>}{error && <p role="alert">{error}</p>}
    {page && <><label>Extracted source text - highlight the relevant passage<textarea className="complaint-source" readOnly value={page.text} onSelect={(event) => setSelection(sourceSelection(page.text, event.target.selectionStart, event.target.selectionEnd))} /></label>
      {selection && <blockquote>{selection.quote}</blockquote>}
      <div className="complaint-grid"><label>Evidence label<input maxLength={120} value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Invoice showing purchase amount" /></label><label>Record type<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="invoice">Invoice / purchase record</option><option value="delivery">Delivery / return record</option><option value="correspondence">Seller correspondence</option><option value="other">Other</option></select></label></div>
      <button type="button" disabled={disabled || !selection || !label.trim()} onClick={() => {
        onAdd({ evidence_id: `e-${crypto.randomUUID()}`, document_id: page.document_id, page_number: page.page_number, start: selection.start, end: selection.end, page_text_sha256: page.page_text_sha256, label: label.trim(), category });
        setSelection(null); setLabel("");
      }}>Add selected excerpt</button></>}
  </div>;
}
