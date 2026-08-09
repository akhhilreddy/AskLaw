import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  MoreHorizontal,
  Scale,
  Trash2,
  X,
  Pencil,
} from "lucide-react";

import { logout } from "../../services/authService";

function Sidebar({
  onNewChat,
  conversations,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  userName,
}) {
  const navigate = useNavigate();

  const [openMenu, setOpenMenu] = useState(null);

  // Delete modal
  const [conversationToDelete, setConversationToDelete] =
    useState(null);

  const [isDeleting, setIsDeleting] = useState(false);

  // Rename modal
  const [conversationToRename, setConversationToRename] =
    useState(null);

  const [renameTitle, setRenameTitle] = useState("");

  const [isRenaming, setIsRenaming] = useState(false);

  // =====================================================
  // LOGOUT
  // =====================================================

  const handleLogout = async () => {
    try {
      await logout();

      navigate("/login");
    } catch (error) {
      console.error("Logout failed:", error);

      localStorage.removeItem("token");

      navigate("/login");
    }
  };

  // =====================================================
  // RENAME
  // =====================================================

  const openRenameModal = (
    conversation,
    event
  ) => {
    event.stopPropagation();

    setOpenMenu(null);

    setConversationToRename(conversation);

    setRenameTitle(
      conversation.title || ""
    );
  };

  const closeRenameModal = () => {
    if (isRenaming) return;

    setConversationToRename(null);

    setRenameTitle("");
  };

  const handleRename = async () => {
    if (!conversationToRename) {
      return;
    }

    const trimmedTitle =
      renameTitle.trim();

    if (!trimmedTitle) {
      return;
    }

    try {
      setIsRenaming(true);

      await onRenameConversation(
        conversationToRename.id,
        trimmedTitle
      );

      // Close modal only after successful API request
      setConversationToRename(null);
      setRenameTitle("");
    } catch (error) {
      console.error(
        "Failed to rename conversation:",
        error
      );
    } finally {
      setIsRenaming(false);
    }
  };

  // =====================================================
  // DELETE
  // =====================================================

  const openDeleteModal = (
    conversation,
    event
  ) => {
    event.stopPropagation();

    setOpenMenu(null);

    setConversationToDelete(
      conversation
    );
  };

  const closeDeleteModal = () => {
    if (isDeleting) return;

    setConversationToDelete(null);
  };

  const handleDelete = async () => {
    if (!conversationToDelete) {
      return;
    }

    try {
      setIsDeleting(true);

      await onDeleteConversation(
        conversationToDelete.id
      );

      setConversationToDelete(null);
    } catch (error) {
      console.error(
        "Failed to delete conversation:",
        error
      );
    } finally {
      setIsDeleting(false);
    }
  };

  // =====================================================
  // UI
  // =====================================================

  return (
    <>
      <aside className="flex h-full w-64 flex-col border-r border-[#252525] bg-[#171717] text-zinc-100">

        {/* ================================================= */}
        {/* ASKLAW HEADER */}
        {/* ================================================= */}

        <div className="border-b border-[#252525] px-5 py-5">
          <div className="flex items-center gap-3">

            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-100 text-black">
              <Scale
                size={20}
                strokeWidth={2}
              />
            </div>

            <div>
              <h2 className="text-base font-semibold tracking-tight">
                AskLaw
              </h2>

              <p className="text-xs text-zinc-500">
                AI Legal Assistant
              </p>
            </div>

          </div>
        </div>

        {/* ================================================= */}
        {/* NEW CHAT */}
        {/* ================================================= */}

        <div className="p-4">
          <button
            type="button"
            onClick={onNewChat}
            className="w-full rounded-xl border border-[#303030] bg-[#242424] px-4 py-3 text-left text-sm font-medium text-zinc-100 transition hover:border-[#404040] hover:bg-[#2d2d2d]"
          >
            <span className="mr-2 text-zinc-400">
              +
            </span>

            New Chat
          </button>
        </div>

        {/* ================================================= */}
        {/* RECENT CHATS */}
        {/* ================================================= */}

        <div className="flex-1 overflow-y-auto px-4 pb-4">

          <p className="mb-3 px-1 text-xs font-medium uppercase tracking-[0.15em] text-zinc-600">
            Recent Chats
          </p>

          {conversations.length === 0 ? (
            <p className="px-1 text-sm text-zinc-500">
              No conversations yet.
            </p>
          ) : (
            <div className="space-y-1">

              {conversations.map(
                (conversation) => (
                  <div
                    key={conversation.id}
                    className="group relative"
                  >

                    {/* Conversation Button */}
                    <button
                      type="button"
                      onClick={() =>
                        onSelectConversation(
                          conversation.id
                        )
                      }
                      className="w-full truncate rounded-lg px-3 py-2.5 pr-10 text-left text-sm text-zinc-400 transition hover:bg-[#242424] hover:text-zinc-100"
                    >
                      {conversation.title ||
                        "New Chat"}
                    </button>

                    {/* Three Dot Button */}
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();

                        setOpenMenu(
                          (prev) =>
                            prev ===
                            conversation.id
                              ? null
                              : conversation.id
                        );
                      }}
                      className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-zinc-600 opacity-0 transition hover:bg-[#303030] hover:text-zinc-300 group-hover:opacity-100"
                      aria-label="Conversation options"
                    >
                      <MoreHorizontal
                        size={17}
                      />
                    </button>

                    {/* ================================================= */}
                    {/* OPTIONS MENU */}
                    {/* ================================================= */}

                    {openMenu ===
                      conversation.id && (
                      <div className="absolute right-1 top-full z-50 mt-1 w-36 overflow-hidden rounded-lg border border-[#303030] bg-[#202020] p-1 shadow-xl">

                        {/* Rename */}
                        <button
                          type="button"
                          onClick={(event) =>
                            openRenameModal(
                              conversation,
                              event
                            )
                          }
                          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-zinc-300 transition hover:bg-[#2c2c2c]"
                        >
                          <Pencil
                            size={15}
                          />

                          Rename
                        </button>

                        {/* Delete */}
                        <button
                          type="button"
                          onClick={(event) =>
                            openDeleteModal(
                              conversation,
                              event
                            )
                          }
                          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-red-400 transition hover:bg-[#2c2020]"
                        >
                          <Trash2
                            size={15}
                          />

                          Delete
                        </button>

                      </div>
                    )}
                  </div>
                )
              )}

            </div>
          )}
        </div>

        {/* ================================================= */}
        {/* USER + LOGOUT */}
        {/* ================================================= */}

        <div className="border-t border-[#252525] p-4">

          <div className="flex items-center justify-between gap-3">

            <div className="min-w-0">

              <p className="truncate text-sm font-medium text-zinc-200">
                {userName || "User"}
              </p>

              <p className="text-xs text-zinc-600">
                Account
              </p>

            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="shrink-0 rounded-lg px-2 py-1.5 text-sm text-zinc-500 transition hover:bg-[#242424] hover:text-red-400"
            >
              Logout
            </button>

          </div>

        </div>

      </aside>

      {/* ===================================================== */}
      {/* RENAME MODAL */}
      {/* ===================================================== */}

      {conversationToRename && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
          onClick={closeRenameModal}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-[#303030] bg-[#202020] p-6 shadow-2xl"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            {/* Header */}
            <div className="flex items-start justify-between gap-4">

              <div>

                <h2 className="text-lg font-semibold text-zinc-100">
                  Rename conversation
                </h2>

                <p className="mt-2 text-sm leading-6 text-zinc-500">
                  Give this conversation a name
                  you'll recognize later.
                </p>

              </div>

              <button
                type="button"
                onClick={closeRenameModal}
                disabled={isRenaming}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-[#303030] hover:text-zinc-200 disabled:opacity-50"
              >
                <X size={18} />
              </button>

            </div>

            {/* Input */}
            <input
              autoFocus
              value={renameTitle}
              onChange={(event) =>
                setRenameTitle(
                  event.target.value
                )
              }
              onKeyDown={(event) => {

                if (
                  event.key === "Enter" &&
                  !isRenaming
                ) {
                  event.preventDefault();

                  handleRename();
                }

                if (
                  event.key === "Escape" &&
                  !isRenaming
                ) {
                  closeRenameModal();
                }

              }}
              maxLength={80}
              placeholder="Conversation title"
              className="mt-5 w-full rounded-xl border border-[#353535] bg-[#181818] px-4 py-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-zinc-500"
            />

            {/* Character Count */}
            <div className="mt-2 text-right text-xs text-zinc-600">
              {renameTitle.length}/80
            </div>

            {/* Buttons */}
            <div className="mt-5 flex justify-end gap-3">

              {/* Cancel */}
              <button
                type="button"
                onClick={closeRenameModal}
                disabled={isRenaming}
                className="rounded-xl border border-[#303030] px-4 py-2.5 text-sm font-medium text-zinc-400 transition hover:bg-[#2a2a2a] hover:text-zinc-100 disabled:opacity-50"
              >
                Cancel
              </button>

              {/* SAVE */}
              <button
                type="button"
                onClick={handleRename}
                disabled={
                  isRenaming ||
                  !renameTitle.trim()
                }
                className="flex min-w-[80px] items-center justify-center rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-medium text-black transition hover:bg-white disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
              >
                {isRenaming
                  ? "Saving..."
                  : "Save"}
              </button>

            </div>

          </div>
        </div>
      )}

      {/* ===================================================== */}
      {/* DELETE MODAL */}
      {/* ===================================================== */}

      {conversationToDelete && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
          onClick={closeDeleteModal}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-[#303030] bg-[#202020] p-6 shadow-2xl"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            {/* Header */}
            <div className="flex items-start justify-between gap-4">

              <div>

                <h2 className="text-lg font-semibold text-zinc-100">
                  Delete conversation?
                </h2>

                <p className="mt-2 text-sm leading-6 text-zinc-500">
                  This conversation will be
                  permanently deleted. This action
                  cannot be undone.
                </p>

              </div>

              <button
                type="button"
                onClick={closeDeleteModal}
                disabled={isDeleting}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-[#303030] hover:text-zinc-200 disabled:opacity-50"
              >
                <X size={18} />
              </button>

            </div>

            {/* Conversation Preview */}
            <div className="mt-5 rounded-xl border border-[#303030] bg-[#181818] px-4 py-3">
              <p className="truncate text-sm text-zinc-300">
                {conversationToDelete.title ||
                  "New Chat"}
              </p>
            </div>

            {/* Buttons */}
            <div className="mt-6 flex justify-end gap-3">

              {/* Cancel */}
              <button
                type="button"
                onClick={closeDeleteModal}
                disabled={isDeleting}
                className="rounded-xl border border-[#303030] px-4 py-2.5 text-sm font-medium text-zinc-400 transition hover:bg-[#2a2a2a] hover:text-zinc-100 disabled:opacity-50"
              >
                Cancel
              </button>

              {/* Delete */}
              <button
                type="button"
                onClick={handleDelete}
                disabled={isDeleting}
                className="flex min-w-[90px] items-center justify-center rounded-xl bg-red-500 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-600 disabled:opacity-50"
              >
                {isDeleting
                  ? "Deleting..."
                  : "Delete"}
              </button>

            </div>

          </div>
        </div>
      )}
    </>
  );
}

export default Sidebar;