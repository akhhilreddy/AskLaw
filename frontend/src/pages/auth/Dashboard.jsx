import AppLayout from "../../layout/AppLayout";
import ChatWindow from "../../components/dashboard/ChatWindow";
import ChatInput from "../../components/dashboard/ChatInput";

import useChat from "../../hooks/useChat";

function Dashboard() {
  const {
    messages,
    conversations,
    isTyping,
    isStreaming,
    sendMessage,
    stop,
    createConversation,
    loadConversation,
  } = useChat();

  return (
    <AppLayout
      onNewChat={createConversation}
      conversations={conversations}
      onSelectConversation={loadConversation}
    >
      <div className="flex h-full flex-col">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
        />

        <ChatInput
          onSendMessage={sendMessage}
          onStopStreaming={stop}
          isStreaming={isStreaming}
        />
      </div>
    </AppLayout>
  );
}

export default Dashboard;