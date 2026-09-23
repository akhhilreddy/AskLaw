import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import AppLayout from "../../layout/AppLayout";
import ChatWindow from "../../components/dashboard/ChatWindow";
import ChatInput from "../../components/dashboard/ChatInput";
import useChat from "../../hooks/useChat";
import { getMe } from "../../services/authService";
import api from "../../services/api";

const suggestions = [
  "What does Article 32 provide?",
  "What is the latest Supreme Court judgment on privacy?",
  "Explain Article 32 and recent developments.",
];

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const documentId = searchParams.get("document_id");
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [documentContextError, setDocumentContextError] = useState("");
  const [userName, setUserName] = useState("Account");

  const {
    conversation,
    messages,
    conversations,
    isTyping,
    isStreaming,
    sendMessage,
    stop,
    createConversation,
    loadConversation,
    deleteConversation,
    renameConversation,
  } = useChat({ documentId });

  useEffect(() => {
    const loadUser = async () => {
      try {
        const user = await getMe();
        if (user?.name) setUserName(user.name);
      } catch (error) {
        console.error("Failed to load user:", error);
      }
    };

    loadUser();
  }, []);

  useEffect(() => {
    if (!documentId) {
      return;
    }

    let active = true;

    const loadSelectedDocument = async () => {
      try {
        const response = await api.get("/documents");
        const document = Array.isArray(response.data)
          ? response.data.find((item) => item.document_id === documentId)
          : null;

        if (!active) return;

        if (document) {
          setSelectedDocument(document);
          setDocumentContextError("");
        } else {
          setSelectedDocument(null);
          setDocumentContextError("This document is not available in your library.");
        }
      } catch (error) {
        if (!active) return;

        setDocumentContextError(
          error.response?.data?.detail ||
            "Could not load the selected document."
        );
      }
    };

    loadSelectedDocument();

    return () => {
      active = false;
    };
  }, [documentId]);

  const title =
    messages.length && conversation.title?.toLowerCase() !== "new chat"
      ? conversation.title
      : "";

  return (
    <AppLayout
      onNewChat={createConversation}
      conversations={conversations}
      onSelectConversation={loadConversation}
      onDeleteConversation={deleteConversation}
      onRenameConversation={renameConversation}
      userName={userName}
      title={title}
    >
      <div className="chat-workspace">
        {documentId && (
          <div className="document-context" role="status">
            <FileText size={15} aria-hidden="true" />
            <span>
              <span className="eyebrow">Researching</span>
              <strong>
                {selectedDocument?.filename ||
                  (documentContextError
                    ? documentContextError
                    : "Loading selected document…")}
              </strong>
            </span>
          </div>
        )}

        {messages.length ? (
          <ChatWindow messages={messages} isTyping={isTyping} />
        ) : (
          <div className="empty-chat">
            <div className="empty-inner">
              <span className="eyebrow">New research</span>
              <h1>What would you like to understand?</h1>
              <p>
                Research Indian law with your documents, current web sources,
                or both. Start with a question and follow the evidence.
              </p>
              <div className="suggestions">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => sendMessage(suggestion)}
                    disabled={isStreaming}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        <ChatInput
          onSendMessage={sendMessage}
          onStopStreaming={stop}
          isStreaming={isStreaming}
        />
      </div>
    </AppLayout>
  );
}
