import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";

function ChatWindow({ messages, isTyping }) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, isTyping]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <h1 className="text-6xl font-semibold tracking-tight text-zinc-100">
            Akhil,
          </h1>

          <p className="mt-5 text-2xl text-zinc-400">
            What can I help you with today?
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-8 py-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
          />
        ))}

        {isTyping && (
          <div className="flex justify-start animate-fade-in">
            <div className="rounded-3xl border border-[#303030] bg-[#202020] px-6 py-4">
              <div className="flex items-center gap-3">
                <span className="text-zinc-400 font-medium">
                  ⚖️ AskLaw is thinking
                </span>

                <div className="flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-500"></span>
                  <span
                    className="h-2 w-2 animate-bounce rounded-full bg-zinc-500"
                    style={{ animationDelay: "0.15s" }}
                  ></span>
                  <span
                    className="h-2 w-2 animate-bounce rounded-full bg-zinc-500"
                    style={{ animationDelay: "0.3s" }}
                  ></span>
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}

export default ChatWindow;