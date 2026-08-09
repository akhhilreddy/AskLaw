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

    deleteConversation,
    renameConversation,
  } = useChat();

  const [userName, setUserName] =
    useState("there");

  const [welcomeIndex, setWelcomeIndex] =
    useState(0);

  // -----------------------------------------
  // Load logged-in user
  // -----------------------------------------

  useEffect(() => {
    const loadUser = async () => {
      try {
        const user = await getMe();

        if (user?.name) {
          setUserName(user.name);
        }
      } catch (error) {
        console.error(
          "Failed to load user:",
          error
        );
      }
    };

    loadUser();
  }, []);

  // -----------------------------------------
  // Rotate welcome message
  // -----------------------------------------

  useEffect(() => {
    const interval = setInterval(() => {
      setWelcomeIndex(
        (prev) =>
          (prev + 1) %
          welcomeMessages.length
      );
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const hasMessages =
    messages.length > 0;

  return (
    <AppLayout
      onNewChat={createConversation}
      conversations={conversations}
      onSelectConversation={
        loadConversation
      }
      onDeleteConversation={
        deleteConversation
      }
      onRenameConversation={
        renameConversation
      }
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
            <div className="w-full max-w-3xl text-center">
              <p className="mb-5 text-[11px] font-medium uppercase tracking-[0.35em] text-zinc-600">
                AskLaw
              </p>

              <h1 className="font-serif text-6xl font-normal leading-tight tracking-[-0.03em] text-zinc-100 md:text-7xl">
                Hello,{" "}
                <span className="text-zinc-400">
                  {userName}
                </span>
              </h1>

              <p
                key={welcomeIndex}
                className="mt-6 text-2xl font-light leading-relaxed tracking-[-0.01em] text-zinc-400 transition-opacity duration-700 md:text-3xl"
              >
                {
                  welcomeMessages[
                    welcomeIndex
                  ]
                }
              </p>

              <p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-zinc-600">
                Ask about contracts,
                employment, property,
                rights, or any legal
                concept you want explained
                in simple language.
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