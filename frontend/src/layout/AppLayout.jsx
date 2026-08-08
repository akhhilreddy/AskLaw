import Sidebar from "../components/dashboard/Sidebar";

function AppLayout({
  children,
  onNewChat,
  conversations,
  onSelectConversation,
  userName,
}) {
  return (
    <div className="flex h-screen bg-[#1A1A1A]">
      <Sidebar
        onNewChat={onNewChat}
        conversations={conversations}
        onSelectConversation={onSelectConversation}
        userName={userName}
      />

      <main className="flex-1 bg-[#1A1A1A]">
        {children}
      </main>
    </div>
  );
}

export default AppLayout;