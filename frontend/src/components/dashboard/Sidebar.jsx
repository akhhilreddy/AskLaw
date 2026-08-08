import { useNavigate } from "react-router-dom";
import { Scale } from "lucide-react";
import { logout } from "../../services/authService";

function Sidebar({
  onNewChat,
  conversations,
  onSelectConversation,
  userName,
}) {
  const navigate = useNavigate();

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

  return (
    <aside className="flex h-full w-64 flex-col border-r border-[#252525] bg-[#171717] text-zinc-100">
      {/* AskLaw Header */}
      <div className="border-b border-[#252525] px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-100 text-black">
            <Scale size={20} strokeWidth={2} />
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

      {/* New Chat */}
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

      {/* Recent Chats */}
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
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                onClick={() =>
                  onSelectConversation(conversation.id)
                }
                className="w-full truncate rounded-lg px-3 py-2.5 text-left text-sm text-zinc-400 transition hover:bg-[#242424] hover:text-zinc-100"
              >
                {conversation.title || "New Chat"}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* User + Logout */}
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
  );
}

export default Sidebar;