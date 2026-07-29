import { useState } from "react";

import AppLayout from "../../layout/AppLayout";
import ChatWindow from "../../components/dashboard/ChatWindow";
import ChatInput from "../../components/dashboard/ChatInput";

function Dashboard() {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);

  const handleSendMessage = (message) => {
    const userMessage = {
      role: "user",
      content: message,
    };

    setMessages((prev) => [...prev, userMessage]);

    setIsTyping(true);

    setTimeout(() => {
      const assistantMessage = {
        role: "assistant",
        content:
          "This is a sample AI response. We'll connect FastAPI next.",
      };

      setMessages((prev) => [...prev, assistantMessage]);

      setIsTyping(false);
    }, 1500);
  };

  return (
    <AppLayout>
      <div className="flex h-full flex-col">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
        />

        <ChatInput
          onSendMessage={handleSendMessage}
        />
      </div>
    </AppLayout>
  );
}

export default Dashboard;