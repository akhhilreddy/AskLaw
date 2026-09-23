import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  RefreshCw,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { Link } from "react-router-dom";
import AppLayout from "../layout/AppLayout";
import { getMe } from "../services/authService";
import api from "../services/api";

const statusLabels = {
  uploaded: "Uploaded",
  processing: "Processing",
  indexed: "Indexed",
  failed: "Indexing failed",
};

function formatUploadDate(value) {
  if (!value) return null;

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return null;

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function Documents() {
  const [userName, setUserName] = useState("Account");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState("");
  const inputRef = useRef(null);

  const loadDocuments = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoadingDocuments(true);
      setLibraryError("");
    }

    try {
      const response = await api.get("/documents");
      setDocuments(Array.isArray(response.data) ? response.data : []);
    } catch (requestError) {
      if (!silent) {
        setLibraryError(
          requestError.response?.data?.detail ||
            "Could not load your document library. Please try again."
        );
      }
    } finally {
      if (!silent) setLoadingDocuments(false);
    }
  }, []);

  useEffect(() => {
    getMe()
      .then((user) => {
        if (user?.name) setUserName(user.name);
      })
      .catch((loadError) => console.error("Failed to load user:", loadError));

    const loadTimer = window.setTimeout(
      loadDocuments,
      0
    );

    return () => window.clearTimeout(
      loadTimer
    );
  }, [loadDocuments]);

  useEffect(() => {
    const hasPendingDocument = documents.some((document) =>
      ["uploaded", "processing"].includes(document.status || "uploaded")
    );

    if (!hasPendingDocument) return undefined;

    const pollTimer = window.setInterval(() => {
      loadDocuments({ silent: true });
    }, 3000);

    return () => window.clearInterval(pollTimer);
  }, [documents, loadDocuments]);

  const handleFileChange = (event) => {
    const selectedFile = event.target.files?.[0] || null;

    setUploadError("");
    setUploadResult(null);

    if (!selectedFile) {
      setFile(null);
      return;
    }

    const isPdf =
      selectedFile.type === "application/pdf" ||
      selectedFile.name.toLowerCase().endsWith(".pdf");

    if (!isPdf) {
      setFile(null);
      inputRef.current.value = "";
      setUploadError("Only PDF files are supported.");
      return;
    }

    setFile(selectedFile);
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!file || uploading) return;

    setUploadError("");
    setUploadResult(null);
    setUploading(true);

    try {
      const body = new FormData();
      body.append("file", file);

      const response = await api.post("/documents/upload", body);

      setUploadResult(response.data);
      setFile(null);
      inputRef.current.value = "";
      await loadDocuments();
    } catch (requestError) {
      setUploadError(
        requestError.response?.data?.detail ||
          "Upload failed. Please try again."
      );
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteCandidate || deletingId) return;

    setDeleteError("");
    setDeletingId(deleteCandidate.document_id);

    try {
      await api.delete(`/documents/${encodeURIComponent(deleteCandidate.document_id)}`);
      setDocuments((current) =>
        current.filter(
          (document) => document.document_id !== deleteCandidate.document_id
        )
      );
      setDeleteCandidate(null);
    } catch (requestError) {
      setDeleteError(
        requestError.response?.data?.detail ||
          "Could not delete this document. Please try again."
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <AppLayout userName={userName} section="Documents">
      <div className="document-page">
        <header className="document-intro">
          <span className="eyebrow">Your research material</span>
          <h1>Documents</h1>
          <p>
            Upload a PDF to add its contents to AskLAW&apos;s document research.
            Once indexing completes, you can ask questions about it in Chat.
          </p>
        </header>

        <form className="upload-panel" onSubmit={handleUpload} aria-busy={uploading}>
          <UploadCloud size={28} color="#192b40" strokeWidth={1.6} />
          <h2>Bring a document into your research.</h2>
          <p>PDF files only. The document is processed and indexed after upload.</p>

          <label className="eyebrow" htmlFor="document-file">
            Choose a PDF
          </label>
          <input
            ref={inputRef}
            id="document-file"
            type="file"
            accept="application/pdf,.pdf"
            onChange={handleFileChange}
            disabled={uploading}
          />

          {file && (
            <div className="upload-row selected-file-row" aria-live="polite">
              <strong>
                <FileText
                  size={15}
                  style={{
                    display: "inline",
                    verticalAlign: "middle",
                    marginRight: 8,
                  }}
                />
                {file.name}
              </strong>
              <span>Ready to upload</span>
            </div>
          )}

          {uploadError && (
            <p className="field-error" role="alert">
              {uploadError}
            </p>
          )}

          <button
            className="primary-button"
            type="submit"
            disabled={!file || uploading}
          >
            {uploading ? "Uploading…" : "Upload document"}
          </button>
        </form>

        {uploadResult && (
          <section className="upload-list upload-success" aria-live="polite">
            <span className="eyebrow">Upload complete</span>
            <div className="upload-row">
              <strong>
                <CheckCircle2
                  size={16}
                  color="#2e765e"
                  style={{
                    display: "inline",
                    verticalAlign: "middle",
                    marginRight: 8,
                  }}
                />
                {uploadResult.filename}
              </strong>
              <span>Indexing started</span>
            </div>
            <p className="upload-success-message">
              {uploadResult.message}
            </p>
            <div className="document-metadata">
              {uploadResult.document_id && (
                <span>Document ID: {uploadResult.document_id}</span>
              )}
              {uploadResult.page_count != null && (
                <span>{uploadResult.page_count} pages</span>
              )}
              {uploadResult.character_count != null && (
                <span>{uploadResult.character_count} characters</span>
              )}
              {uploadResult.chunk_count != null && (
                <span>{uploadResult.chunk_count} chunks</span>
              )}
            </div>
          </section>
        )}

        <section
          className="upload-list document-library"
          aria-labelledby="document-library-title"
          aria-busy={loadingDocuments}
        >
          <div className="library-header">
            <div>
              <span className="eyebrow">Saved documents</span>
              <h2 id="document-library-title">
                Document library
              </h2>
            </div>
            <button
              type="button"
              className="text-link library-refresh"
              onClick={loadDocuments}
              disabled={loadingDocuments}
            >
              <RefreshCw
                size={14}
                className={loadingDocuments ? "animate-spin" : ""}
              />
              Refresh
            </button>
          </div>

          {loadingDocuments && (
            <div className="library-state library-loading" role="status">
              <strong>Loading your documents…</strong>
            </div>
          )}

          {!loadingDocuments && libraryError && (
            <div className="library-state library-error">
              <p className="field-error" role="alert">
                {libraryError}
              </p>
              <button
                type="button"
                className="text-link"
                onClick={loadDocuments}
              >
                Try again
              </button>
            </div>
          )}

          {!loadingDocuments && !libraryError && documents.length === 0 && (
            <div className="library-state library-empty">
              <strong>
                Your document library is empty.
              </strong>
              <p>
                Upload a PDF to start document research.
              </p>
            </div>
          )}

          {!loadingDocuments &&
            !libraryError &&
            documents.map((document) => {
              const status = document.status || "uploaded";
              const uploadedAt = formatUploadDate(document.uploaded_at);
              const documentType =
                document.content_type === "application/pdf"
                  ? "PDF"
                  : document.content_type;

              return (
                <article className="upload-row document-row" key={document.document_id}>
                  <div className="document-summary">
                    <strong className="document-name">
                      <FileText size={15} aria-hidden="true" />
                      <span>
                        {document.filename}
                      </span>
                    </strong>
                    <span className="document-meta-line">
                      {documentType && <span>{documentType}</span>}
                      {document.page_count != null && (
                        <span>{document.page_count} pages</span>
                      )}
                      {document.chunk_count != null && (
                        <span>{document.chunk_count} chunks</span>
                      )}
                      {uploadedAt && <span>{uploadedAt}</span>}
                    </span>
                    {status === "processing" && (
                      <span className="document-status-note">
                        This document is still being indexed.
                      </span>
                    )}
                    {status === "failed" && (
                      <span className="document-status-note error">
                        Document indexing failed.
                      </span>
                    )}
                  </div>
                  <div className="document-actions">
                    <span className={`document-status status-${status}`}>
                      {statusLabels[status] || status}
                    </span>
                    {status === "indexed" && (
                      <Link
                        className="primary-button document-research-button"
                        to={`/dashboard?document_id=${encodeURIComponent(
                          document.document_id
                        )}`}
                      >
                        Research
                        <ArrowRight size={13} aria-hidden="true" />
                      </Link>
                    )}
                    <button
                      type="button"
                      className="document-delete-button"
                      onClick={() => {
                        setDeleteError("");
                        setDeleteCandidate(document);
                      }}
                      disabled={
                        deletingId === document.document_id ||
                        status === "uploaded" ||
                        status === "processing"
                      }
                      title={
                        status === "uploaded" || status === "processing"
                          ? "This document is still being indexed."
                          : `Delete ${document.filename}`
                      }
                      aria-label={`Delete ${document.filename}`}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Delete
                    </button>
                  </div>
                </article>
              );
            })}
        </section>

        <p className="document-chat-link">
          <Link className="text-link" to="/dashboard">
            Go to chat <ArrowRight size={13} style={{ display: "inline" }} />
          </Link>
        </p>
      </div>

      {deleteCandidate && (
        <div className="modal-backdrop" role="presentation">
          <div
            className="modal delete-document-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-document-title"
          >
            <h2 id="delete-document-title">Delete document?</h2>
            <p>
              This removes <strong>{deleteCandidate.filename}</strong> and its
              indexed research data. This action cannot be undone.
            </p>
            {deleteError && (
              <p className="field-error" role="alert">
                {deleteError}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                onClick={() => setDeleteCandidate(null)}
                disabled={Boolean(deletingId)}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={Boolean(deletingId)}
              >
                {deletingId ? "Deleting…" : "Delete document"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
