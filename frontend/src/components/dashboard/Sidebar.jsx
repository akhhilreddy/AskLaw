function Sidebar() {
  return (
   <aside className="w-72 text-zinc-100 border-r border-[#2A2A2A] flex flex-col justify-between">
      {/* Logo */}
      <div className="p-5 border-b border-zinc-800">
        AskLaw
      </div>

      {/* New Chat */}
      <div className="p-4">
        New Chat
      </div>

      {/* Chat List */}
      <div className="flex-1 p-4">
        Recent Chats
      </div>

      {/* User */}
      <div className="p-4 border-t border-zinc-800">
        Akhil
      </div>
    </aside>
  );
}

export default Sidebar;