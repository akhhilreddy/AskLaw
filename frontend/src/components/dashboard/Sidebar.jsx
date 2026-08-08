function Sidebar({
  onNewChat,
  conversations,
  onSelectConversation,
}) {
  return (
    <aside className="flex h-full w-64 flex-col bg-[#171717] text-zinc-100">
      {/* New Chat */}
      <div className="p-4">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full rounded-xl border border-[#303030] bg-[#242424] px-4 py-3 text-left text-sm font-medium text-zinc-100 transition hover:bg-[#2d2d2d]"
        >
          + New Chat
        </button>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-3 text-xs font-medium uppercase tracking-wide text-zinc-500">
          Recent Chats
        </p>

        {conversations.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No conversations yet.
          </p>
        ) : (
          <div className="space-y-1">
            {conversations.map((conversation) => (
              <button
                key={conversation._id || conversation.id}
                type="button"
                onClick={() =>
                  onSelectConversation(
                    conversation._id || conversation.id
                  )
                }
                className="w-full truncate rounded-lg px-3 py-2 text-left text-sm text-zinc-400 transition hover:bg-[#242424] hover:text-zinc-100"
              >
                {conversation.title || "New Chat"}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* User */}
      <div className="border-t border-zinc-800 p-4">
        <p className="text-sm text-zinc-300">
          Akhil
        </p>
      </div>
    </aside>
  );
}

export default Sidebar;