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
            ? "bg-[#2A2A2A] border-[#3A3A3A] text-zinc-100"
            : "bg-[#202020] border-[#303030] text-zinc-100"
        }`}
      >
        <p className="leading-7 whitespace-pre-wrap break-words">
          {message.content}
        </p>
      </div>
    </div>
  );
}

export default ChatMessage;