import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  FileText,
  MessageSquareText,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import Logo from "../common/Logo";
import SidebarRail from "./SidebarRail";
import { logout } from "../../services/authService";

const focusableSelector =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Sidebar({
  open,
  collapsed,
  isMobile,
  onClose,
  onCollapse,
  closeButtonRef,
  railExpandRef,
  onNewChat,
  conversations,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  userName,
}) {
  const showRecent = Array.isArray(conversations);
  conversations = conversations || [];

  const navigate = useNavigate();
  const [openMenu, setOpenMenu] = useState(null);
  const [conversationToDelete, setConversationToDelete] = useState(null);
  const [conversationToRename, setConversationToRename] = useState(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [modalError, setModalError] = useState("");
  const optionsButtonRefs = useRef(new Map());
  const modalTriggerRef = useRef(null);
  const renameDialogRef = useRef(null);
  const renameInputRef = useRef(null);
  const deleteDialogRef = useRef(null);
  const deleteCancelRef = useRef(null);
  const newChatRef = useRef(null);
  const hasOpenDialog = Boolean(conversationToRename || conversationToDelete);

  const restoreModalFocus = useCallback(() => {
    const trigger = modalTriggerRef.current;
    modalTriggerRef.current = null;

    window.requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
      else newChatRef.current?.focus();
    });
  }, []);

  const closeRenameDialog = useCallback(
    (force = false) => {
      if (isRenaming && !force) return;
      setConversationToRename(null);
      setRenameTitle("");
      restoreModalFocus();
    },
    [isRenaming, restoreModalFocus]
  );

  const closeDeleteDialog = useCallback(
    (force = false) => {
      if (isDeleting && !force) return;
      setConversationToDelete(null);
      restoreModalFocus();
    },
    [isDeleting, restoreModalFocus]
  );

  useEffect(() => {
    if (conversationToRename) renameInputRef.current?.focus();
  }, [conversationToRename]);

  useEffect(() => {
    if (conversationToDelete) deleteCancelRef.current?.focus();
  }, [conversationToDelete]);

  useEffect(() => {
    if (!hasOpenDialog) return undefined;

    const workspace = document.querySelector(".workspace-main");
    if (!workspace) return undefined;

    const wasInert = workspace.inert;
    workspace.inert = true;

    return () => {
      workspace.inert = wasInert;
    };
  }, [hasOpenDialog]);

  useEffect(() => {
    if (!hasOpenDialog) return undefined;

    const handleDialogKeyDown = (event) => {
      const dialog = conversationToRename
        ? renameDialogRef.current
        : deleteDialogRef.current;

      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();

        if (conversationToRename) closeRenameDialog();
        else closeDeleteDialog();
        return;
      }

      if (event.key !== "Tab" || !dialog) return;

      const focusableElements = Array.from(
        dialog.querySelectorAll(focusableSelector)
      );

      if (focusableElements.length === 0) {
        event.preventDefault();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      } else if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener("keydown", handleDialogKeyDown, true);
    return () =>
      document.removeEventListener("keydown", handleDialogKeyDown, true);
  }, [
    closeDeleteDialog,
    closeRenameDialog,
    conversationToDelete,
    conversationToRename,
    hasOpenDialog,
  ]);

  const handleNewChat = () => {
    onNewChat?.();
    navigate("/dashboard");
    onClose?.();
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error("Logout failed:", error);
      localStorage.removeItem("token");
    }
    navigate("/login");
  };

  const openRenameDialog = (conversation) => {
    modalTriggerRef.current = optionsButtonRefs.current.get(conversation.id);
    setConversationToRename(conversation);
    setRenameTitle(conversation.title || "");
    setOpenMenu(null);
    setModalError("");
  };

  const openDeleteDialog = (conversation) => {
    modalTriggerRef.current = optionsButtonRefs.current.get(conversation.id);
    setConversationToDelete(conversation);
    setOpenMenu(null);
    setModalError("");
  };

  const handleRename = async () => {
    if (!conversationToRename || !renameTitle.trim()) return;

    try {
      setIsRenaming(true);
      setModalError("");
      await onRenameConversation(conversationToRename.id, renameTitle.trim());
      setConversationToRename(null);
      setRenameTitle("");
      restoreModalFocus();
    } catch (error) {
      console.error("Failed to rename conversation:", error);
      setModalError("Could not rename this research. Please try again.");
    } finally {
      setIsRenaming(false);
    }
  };

  const handleDelete = async () => {
    if (!conversationToDelete) return;

    try {
      setIsDeleting(true);
      setModalError("");
      await onDeleteConversation(conversationToDelete.id);
      setConversationToDelete(null);
      restoreModalFocus();
    } catch (error) {
      console.error("Failed to delete conversation:", error);
      setModalError("Could not delete this research. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <aside
        className={`sidebar ${open ? "open" : ""} ${collapsed ? "collapsed" : ""}`}
        inert={hasOpenDialog || (!open && isMobile)}
      >
        {collapsed && (
          <SidebarRail
            expandRef={railExpandRef}
            onExpand={onCollapse}
            onNewChat={handleNewChat}
            onClose={onClose}
            showRecent={showRecent}
            userName={userName}
          />
        )}
        <div className="sidebar-header">
          <Logo to="/dashboard" />
          <button
            ref={closeButtonRef}
            type="button"
            className="sidebar-collapse-button"
            onClick={onCollapse}
            aria-label={isMobile ? "Close sidebar" : "Collapse sidebar"}
          >
            <PanelLeftClose size={18} strokeWidth={1.7} />
          </button>
        </div>
        <div className="sidebar-primary">
          <button ref={newChatRef} className="new-research" onClick={handleNewChat}>
            <Plus size={17} /> New chat
          </button>
          <nav className="sidebar-nav" aria-label="Workspace navigation">
            <NavLink
              to="/dashboard"
              onClick={onClose}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              <MessageSquareText size={17} /> Chat
            </NavLink>
            <NavLink
              to="/documents"
              onClick={onClose}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              <FileText size={17} /> Documents
            </NavLink>
          </nav>
        </div>

        {showRecent && (
          <>
            <div className="sidebar-label">Recent chats</div>
            <div className="conversation-list">
              {conversations.length === 0 ? (
                <p style={{ fontSize: 12, color: "#8b998e", padding: "0 10px" }}>
                  No conversations yet.
                </p>
              ) : (
                conversations.map((conversation) => (
                  <div className="conversation-item" key={conversation.id}>
                    <button
                      onClick={() => {
                        onSelectConversation?.(conversation.id);
                        navigate("/dashboard");
                        onClose?.();
                      }}
                    >
                      {conversation.title || "New chat"}
                    </button>
                    <button
                      ref={(node) => {
                        if (node) optionsButtonRefs.current.set(conversation.id, node);
                        else optionsButtonRefs.current.delete(conversation.id);
                      }}
                      className="conversation-more"
                      aria-label={`Options for ${conversation.title || "research"}`}
                      aria-expanded={openMenu === conversation.id}
                      onClick={() =>
                        setOpenMenu((previous) =>
                          previous === conversation.id ? null : conversation.id
                        )
                      }
                    >
                      <MoreHorizontal size={16} />
                    </button>
                    {openMenu === conversation.id && (
                      <div className="conversation-menu">
                        <button onClick={() => openRenameDialog(conversation)}>
                          <Pencil size={14} /> Rename
                        </button>
                        <button onClick={() => openDeleteDialog(conversation)}>
                          <Trash2 size={14} /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </>
        )}

        <div className="sidebar-footer">
          <strong>{userName || "Account"}</strong>
          <button onClick={handleLogout}>Sign out</button>
        </div>
      </aside>

      {conversationToRename && (
        <div
          className="modal-backdrop"
          onMouseDown={() => closeRenameDialog()}
        >
          <div
            ref={renameDialogRef}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <h2 id="rename-title">Rename research</h2>
              <button
                aria-label="Close"
                style={{ border: 0, background: "transparent" }}
                onClick={() => closeRenameDialog()}
              >
                <X size={18} />
              </button>
            </div>
            <p>Give this conversation a name you will recognize.</p>
            <input
              ref={renameInputRef}
              value={renameTitle}
              maxLength={80}
              aria-label="Research title"
              onChange={(event) => setRenameTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleRename();
              }}
            />
            {modalError && (
              <p className="field-error" role="alert">
                {modalError}
              </p>
            )}
            <div className="modal-actions">
              <button onClick={() => closeRenameDialog()} disabled={isRenaming}>
                Cancel
              </button>
              <button
                onClick={handleRename}
                disabled={isRenaming || !renameTitle.trim()}
              >
                {isRenaming ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {conversationToDelete && (
        <div
          className="modal-backdrop"
          onMouseDown={() => closeDeleteDialog()}
        >
          <div
            ref={deleteDialogRef}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="delete-title">Delete research?</h2>
            <p>
              “{conversationToDelete.title || "New chat"}” will be permanently
              deleted.
            </p>
            {modalError && (
              <p className="field-error" role="alert">
                {modalError}
              </p>
            )}
            <div className="modal-actions">
              <button
                ref={deleteCancelRef}
                onClick={() => closeDeleteDialog()}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button onClick={handleDelete} disabled={isDeleting}>
                {isDeleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
