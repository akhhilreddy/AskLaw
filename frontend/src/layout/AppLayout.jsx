import Sidebar from "../components/dashboard/Sidebar";

function AppLayout({
  children,
  onNewChat,
  conversations,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  userName,
}) {
  return (
    <div className="flex h-screen bg-[#1A1A1A]">
      <Sidebar
        onNewChat={onNewChat}
        conversations={conversations}
        onSelectConversation={onSelectConversation}
        onDeleteConversation={onDeleteConversation}
        onRenameConversation={onRenameConversation}
        userName={userName}
      />

      <main className="flex-1 bg-[#1A1A1A]">
        {children}
      </main>
    </div>
  );
}

export default AppLayout;