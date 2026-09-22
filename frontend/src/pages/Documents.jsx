import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  RefreshCw,
  UploadCloud,
} from "lucide-react";
import { Link } from "react-router-dom";
import AppLayout from "../layout/AppLayout";
import { getMe } from "../services/authService";
import api from "../services/api";

const statusLabels = {
  uploaded: "Uploaded",
  processing: "Indexing",
  indexed: "Indexed",
  failed: "Indexing failed",
};

const statusColors = {
  uploaded: "#6f7780",
  processing: "#8a6b32",
  indexed: "#2e765e",
  failed: "#af4036",
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
  const inputRef = useRef(null);

  const loadDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    setLibraryError("");

    try {
      const response = await api.get("/documents");
      setDocuments(Array.isArray(response.data) ? response.data : []);
    } catch (requestError) {
      setLibraryError(
        requestError.response?.data?.detail ||
          "Could not load your document library. Please try again."
      );
    } finally {
      setLoadingDocuments(false);
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

  return (
    <AppLayout userName={userName} section="Documents">
      <div className="document-page">
        <span className="eyebrow">Your research material</span>
        <h1>Documents</h1>
        <p>
          Upload a PDF to add its contents to AskLAW&apos;s document research.
          Once indexing completes, you can ask questions about it in Chat.
        </p>

        <form className="upload-panel" onSubmit={handleUpload}>
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
            <div className="upload-row" aria-live="polite">
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
          <section className="upload-list" aria-live="polite">
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
            <p style={{ fontSize: 13, marginTop: 10 }}>
              {uploadResult.message}
            </p>
          </section>
        )}

        <section className="upload-list" aria-labelledby="document-library-title">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
              marginBottom: 8,
            }}
          >
            <div>
              <span className="eyebrow">Saved documents</span>
              <h2
                id="document-library-title"
                style={{
                  font: "400 27px var(--serif)",
                  margin: "7px 0 0",
                }}
              >
                Document library
              </h2>
            </div>
            <button
              type="button"
              className="text-link"
              onClick={loadDocuments}
              disabled={loadingDocuments}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                border: 0,
                background: "transparent",
                padding: 6,
              }}
            >
              <RefreshCw
                size={14}
                className={loadingDocuments ? "animate-spin" : ""}
              />
              Refresh
            </button>
          </div>

          {loadingDocuments && (
            <div className="upload-row" role="status">
              <strong>Loading your documents…</strong>
            </div>
          )}

          {!loadingDocuments && libraryError && (
            <div style={{ padding: "18px 0", borderTop: "1px solid var(--line)" }}>
              <p className="field-error" role="alert" style={{ margin: 0 }}>
                {libraryError}
              </p>
              <button
                type="button"
                className="text-link"
                onClick={loadDocuments}
                style={{
                  border: 0,
                  background: "transparent",
                  padding: "10px 0 0",
                }}
              >
                Try again
              </button>
            </div>
          )}

          {!loadingDocuments && !libraryError && documents.length === 0 && (
            <div
              style={{
                padding: "24px 0",
                borderTop: "1px solid var(--line)",
              }}
            >
              <strong style={{ fontSize: 14 }}>
                Your document library is empty.
              </strong>
              <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 0 }}>
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
                <article className="upload-row" key={document.document_id}>
                  <div style={{ minWidth: 0 }}>
                    <strong
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <FileText size={15} aria-hidden="true" />
                      <span style={{ overflowWrap: "anywhere" }}>
                        {document.filename}
                      </span>
                    </strong>
                    <span
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "4px 12px",
                        marginTop: 7,
                        fontSize: 12,
                      }}
                    >
                      {documentType && <span>{documentType}</span>}
                      {document.page_count != null && (
                        <span>{document.page_count} pages</span>
                      )}
                      {document.chunk_count != null && (
                        <span>{document.chunk_count} chunks</span>
                      )}
                      {uploadedAt && <span>{uploadedAt}</span>}
                    </span>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      flexShrink: 0,
                    }}
                  >
                    <span
                      style={{
                        color: statusColors[status] || "var(--muted)",
                        fontWeight: 650,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {statusLabels[status] || status}
                    </span>
                    {status === "indexed" && (
                      <Link
                        className="primary-button"
                        to={`/dashboard?document_id=${encodeURIComponent(
                          document.document_id
                        )}`}
                        style={{
                          padding: "8px 12px",
                          fontSize: 12,
                        }}
                      >
                        Research
                        <ArrowRight size={13} aria-hidden="true" />
                      </Link>
                    )}
                  </div>
                </article>
              );
            })}
        </section>

        <p style={{ fontSize: 12, marginTop: 28 }}>
          <Link className="text-link" to="/dashboard">
            Go to chat <ArrowRight size={13} style={{ display: "inline" }} />
          </Link>
        </p>
      </div>
    </AppLayout>
  );
}
