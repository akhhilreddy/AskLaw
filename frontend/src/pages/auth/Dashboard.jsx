import AppLayout from "../../layout/AppLayout";
import ChatWindow from "../../components/dashboard/ChatWindow";
import ChatInput from "../../components/dashboard/ChatInput";

import useChat from "../../hooks/useChat";

function Dashboard() {
  const {
    messages,
    isTyping,
    isStreaming,
    sendMessage,
    stop,
  } = useChat();

  return (
    <AppLayout>
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