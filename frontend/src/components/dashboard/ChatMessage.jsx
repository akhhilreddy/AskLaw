import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Globe2,
  Layers3,
  Scale,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import CodeBlock from "./CodeBlock";
import MessageActions from "./MessageActions";

const routeLabels = {
  rag: "Document Research",
  web: "Web Research",
  hybrid: "Hybrid Research",
};

const supportLabels = {
  supported: "Supported",
  partial: "Partially supported",
  unsupported: "Unsupported",
};

function sourceKey(source, index) {
  if (source.source_type === "web") {
    return `web:${source.url || source.title || index}`;
  }

  return `document:${source.document_id || source.filename || index}:${
    source.page_number ?? ""
  }:${source.chunk_index ?? ""}`;
}

function validUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function SourceCard({ source }) {
  const web = source.source_type === "web";
  const name = web ? source.title : source.filename;
  const url = web && validUrl(source.url) ? source.url : null;

  return (
    <article className="source-card">
      <div className="source-type">
        {web ? "Web source" : "Document source"}
      </div>
      <div className="source-title">
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer">
            {name || url}
          </a>
        ) : (
          name || "Source"
        )}
      </div>
      <div className="source-meta">
        {source.page_number != null && <span>Page {source.page_number}</span>}
        {source.chunk_index != null && <span>Chunk {source.chunk_index}</span>}
        {source.score != null && <span>Relevance {source.score}</span>}
        {source.engine && <span>{source.engine}</span>}
        {source.url && <span className="source-url">{source.url}</span>}
      </div>
      {web && source.content && (
        <p className="source-preview">{source.content}</p>
      )}
    </article>
  );
}

function Sources({ sources, route }) {
  const unique = Array.from(
    new Map(
      sources.map((source, index) => [sourceKey(source, index), source])
    ).values()
  );
  const documentSources = unique.filter(
    (source) => source.source_type !== "web"
  );
  const webSources = unique.filter((source) => source.source_type === "web");
  const grouped = route?.toLowerCase() === "hybrid";

  const renderGroup = (label, items) =>
    items.length > 0 && (
      <section className="source-group">
        {grouped && <h4>{label}</h4>}
        <div className="source-grid">
          {items.map((source, index) => (
            <SourceCard
              source={source}
              key={sourceKey(source, index)}
            />
          ))}
        </div>
      </section>
    );

  return (
    <details className="sources">
      <summary>
        <BookOpen size={15} /> Evidence &amp; sources
        <span className="source-count">
          {unique.length} {unique.length === 1 ? "source" : "sources"}
        </span>
      </summary>
      {renderGroup("Document sources", documentSources)}
      {renderGroup("Web sources", webSources)}
    </details>
  );
}

function Verification({ verification }) {
  if (!verification) return null;

  const summary = verification.summary || {};
  const claims = Array.isArray(verification.claims) ? verification.claims : [];
  const groundingScore = Number(verification.grounding_score);
  const scoreLabel = Number.isFinite(groundingScore)
    ? `${Math.round(groundingScore * 100)}%`
    : null;

  const StatusIcon = ({ support }) => {
    if (support === "supported") return <CheckCircle2 size={14} />;
    if (support === "partial") return <AlertTriangle size={14} />;
    return <XCircle size={14} />;
  };

  return (
    <details className="verification">
      <summary>
        <ShieldCheck size={15} /> Evidence verification
        {scoreLabel && (
          <span className="verification-score">{scoreLabel} grounded</span>
        )}
      </summary>
      <div className="verification-summary">
        <span>
          <strong>{summary.total_claims ?? claims.length}</strong> claims checked
        </span>
        <span>
          <strong>{summary.supported_claims ?? 0}</strong> supported
        </span>
        <span>
          <strong>{summary.partial_claims ?? 0}</strong> partial
        </span>
        <span>
          <strong>{summary.unsupported_claims ?? 0}</strong> unsupported
        </span>
      </div>
      {claims.length > 0 && (
        <div className="verification-claims">
          {claims.map((claim, index) => (
            <div
              className={`verification-claim ${claim.support || "unsupported"}`}
              key={claim.claim_id || index}
            >
              <span className="claim-status">
                <StatusIcon support={claim.support} />
                {supportLabels[claim.support] || claim.support || "Unsupported"}
              </span>
              <p>{claim.claim}</p>
            </div>
          ))}
        </div>
      )}
      <p className="verification-note">
        Verification reflects support in the retrieved sources, not legal
        correctness.
      </p>
    </details>
  );
}

export default function ChatMessage({ message }) {
  const isUser = message.role === "user";
  const route = message.route?.toLowerCase();
  const RouteIcon =
    route === "web" ? Globe2 : route === "hybrid" ? Layers3 : BookOpen;

  return (
    <article className={`chat-entry ${isUser ? "user" : "assistant"}`}>
      {isUser ? (
        <div className="user-bubble">{message.content}</div>
      ) : (
        <div>
          <div className="answer-header">
            <span className="answer-mark">
              <Scale size={15} />
            </span>
            AskLAW
            {routeLabels[route] && (
              <span className="research-mode-label">
                <RouteIcon size={13} />
                {routeLabels[route]}
              </span>
            )}
          </div>
          {message.content ? (
            <div className="answer-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children }) {
                    const match = /language-(\w+)/.exec(className || "");
                    return match ? (
                      <CodeBlock language={match[1]}>
                        {String(children).replace(/\n$/, "")}
                      </CodeBlock>
                    ) : (
                      <code>{children}</code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="streaming-line">
              <span className="pulse-dot" /> Generating answer…
            </div>
          )}
          {message.sources?.length > 0 ? (
            <Sources sources={message.sources} route={route} />
          ) : (
            message.isComplete &&
            route && (
              <p className="no-sources">No supporting sources were returned.</p>
            )
          )}
          <Verification verification={message.verification} />
          {message.isComplete && message.content && (
            <MessageActions content={message.content} />
          )}
        </div>
      )}
    </article>
  );
}
