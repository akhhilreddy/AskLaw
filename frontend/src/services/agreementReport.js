export const termLabels = {
  security_deposit: "Security deposit",
  rent_and_payment: "Rent & payment",
  notice_period: "Notice period",
  lock_in: "Lock-in period",
  termination: "Termination",
  renewal: "Renewal",
  deductions_and_charges: "Deductions & charges",
  disputes_and_jurisdiction: "Disputes & jurisdiction",
};

export const changeLabels = {
  changed: "Text changed", added: "Text added", removed: "Text removed", formatting_only: "Whitespace only",
};

export function agreementError(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (error?.response?.status === 429) {
    return `Usage limit reached. Try again in ${error.response.headers?.["retry-after"] || "a few"} seconds.`;
  }
  return "Agreement review is unavailable. Check your connection and try again.";
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

const quoteHtml = (item) => `<blockquote><pre>${escapeHtml(item.quote)}</pre><small>${item.scope === "clause_candidate" ? "Clause candidate · " : item.scope === "context_excerpt" ? "Local context excerpt · " : ""}${item.is_partial ? "Clipped excerpt · " : ""}Document ${escapeHtml(item.document_id)} · page ${escapeHtml(item.page_number)} · characters ${escapeHtml(item.start)}–${escapeHtml(item.end)} (zero-based, end exclusive)<br>Page-text SHA-256: ${escapeHtml(item.page_text_sha256)}</small></blockquote>`;

export function agreementReportHtml(report, sample = false) {
  const comparison = Array.isArray(report.changes);
  const body = comparison
    ? `<p>Original: ${escapeHtml(report.before.title)}<br>Revised: ${escapeHtml(report.after.title)}</p>
       <p>Extracted-text SHA-256 (original): ${escapeHtml(report.before.extracted_text_sha256)}<br>Extracted-text SHA-256 (revised): ${escapeHtml(report.after.extracted_text_sha256)}</p>
       <p>${Object.entries(report.summary).map(([key, count]) => `${escapeHtml(changeLabels[key] || key)}: ${escapeHtml(count)}`).join(" · ")}</p>
       ${report.changes.length ? report.changes.map((change) => `<section><h2>${escapeHtml(changeLabels[change.kind] || change.kind)}</h2><h3>Original</h3>${change.before.map(quoteHtml).join("") || "<p>No original passage.</p>"}<h3>Revised</h3>${change.after.map(quoteHtml).join("") || "<p>No revised passage.</p>"}</section>`).join("") : "<p>No extracted-text differences found. This does not prove the signed PDFs are identical.</p>"}`
    : `<p>${escapeHtml(report.title)}<br>Extracted-text SHA-256: ${escapeHtml(report.extracted_text_sha256)}</p>${report.terms.map((term) => `<section><h2>${escapeHtml(termLabels[term.kind] || term.kind)}</h2>${term.mentions.map(quoteHtml).join("") || "<p>Not identified by keyword matching — not a finding that the term is absent.</p>"}</section>`).join("")}`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>AskLaw — Before You Sign</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 24px;color:#192b40}pre{white-space:pre-wrap;font:inherit;overflow-wrap:anywhere}small,p{overflow-wrap:anywhere}blockquote{margin:16px 0;padding:12px 20px;border-left:3px solid #ac8c52;background:#f6f7f8}section{border-top:1px solid #ddd;padding-top:12px}small{font-size:12px}@media print{body{margin:0;max-width:none}h2,h3{break-after:avoid}}</style></head><body><h1>Before You Sign</h1><p>${sample ? "SYNTHETIC SAMPLE — NOT A LEGAL TEMPLATE. " : ""}Text-only ${comparison ? "version comparison" : "key-term review"}. Analysis version ${escapeHtml(report.analysis_version)}.</p><p>Open this file in a browser and use Print → Save as PDF to keep a printable copy.</p>${body}<h2>Limitations</h2><ul>${report.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><p>${escapeHtml(report.disclaimer)}</p></body></html>`;
}
