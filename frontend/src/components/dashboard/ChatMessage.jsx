import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import CodeBlock from "./CodeBlock";
import MessageActions from "./MessageActions";

function ChatMessage({ message }) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      <div
        className={`max-w-[75%] rounded-3xl border px-6 py-4 transition-all duration-300 ${
          isUser
            ? "border-[#3A3A3A] bg-[#2A2A2A] text-zinc-100"
            : "border-[#303030] bg-[#202020] text-zinc-100"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words leading-7">
            {message.content}
          </p>
        ) : (
          <>
            <div className="prose prose-invert max-w-none break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children }) {
                    const match = /language-(\w+)/.exec(className || "");

                    if (match) {
                      return (
                        <CodeBlock language={match[1]}>
                          {String(children).replace(/\n$/, "")}
                        </CodeBlock>
                      );
                    }

                    return (
                      <code className="rounded bg-zinc-800 px-1 py-0.5 text-sm">
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>

            {message.isComplete && (
              <MessageActions content={message.content} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;