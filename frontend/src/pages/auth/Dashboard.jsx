import { useEffect, useState } from "react";

import AppLayout from "../../layout/AppLayout";
import ChatWindow from "../../components/dashboard/ChatWindow";
import ChatInput from "../../components/dashboard/ChatInput";

import useChat from "../../hooks/useChat";
import { getMe } from "../../services/authService";

const welcomeMessages = [
  "What legal question is on your mind?",
  "Let’s make the law a little easier to understand.",
  "Got a legal question? Ask away.",
  "What would you like to understand today?",
  "Let’s untangle something legal.",
];

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

  const [userName, setUserName] = useState("there");
  const [welcomeIndex, setWelcomeIndex] = useState(0);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const user = await getMe();

        if (user?.name) {
          setUserName(user.name);
        }
      } catch (error) {
        console.error("Failed to load user:", error);
      }
    };

    loadUser();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setWelcomeIndex((prev) =>
        (prev + 1) % welcomeMessages.length
      );
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const hasMessages = messages.length > 0;

  return (
    <AppLayout
      onNewChat={createConversation}
      conversations={conversations}
      onSelectConversation={loadConversation}
      userName={userName}
    >
      <div className="flex h-full flex-col">
        {hasMessages ? (
          <ChatWindow
            messages={messages}
            isTyping={isTyping}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center px-6 pb-20">
            <div className="max-w-2xl text-center">
              <p className="mb-3 text-sm font-medium uppercase tracking-[0.25em] text-zinc-500">
                AskLaw
              </p>

              <h1 className="text-5xl font-semibold tracking-tight text-zinc-100 md:text-6xl">
                Hello,{" "}
                <span className="text-zinc-400">
                  {userName}
                </span>
              </h1>

              <p
                key={welcomeIndex}
                className="mt-5 text-xl font-light tracking-wide text-zinc-400 transition-all duration-500 md:text-2xl"
              >
                {welcomeMessages[welcomeIndex]}
              </p>

              <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-zinc-600">
                Ask about contracts, employment, property,
                rights, or any other legal concept you want
                explained in simple language.
              </p>
            </div>
          </div>
        )}

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