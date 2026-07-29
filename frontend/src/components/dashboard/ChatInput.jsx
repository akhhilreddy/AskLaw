import { useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

function ChatInput({ onSendMessage }) {
  const [message, setMessage] = useState("");

  const textareaRef = useRef(null);

  const handleChange = (e) => {
    setMessage(e.target.value);

    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height =
      textareaRef.current.scrollHeight + "px";
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    const trimmedMessage = message.trim();

    if (!trimmedMessage) return;

    onSendMessage(trimmedMessage);

    setMessage("");

    textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="border-t border-[#2A2A2A] bg-[#1A1A1A] px-8 py-6">
      <form
        onSubmit={handleSubmit}
        className="mx-auto flex max-w-5xl items-end gap-4 rounded-3xl border border-[#303030] bg-[#242424] p-4"
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          placeholder="Ask a legal question..."
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          className="max-h-48 flex-1 resize-none overflow-y-auto bg-transparent text-zinc-100 placeholder:text-zinc-500 outline-none"
        />

        <button
          type="submit"
          disabled={!message.trim()}
          className={`flex h-11 w-11 items-center justify-center rounded-full transition ${
            message.trim()
              ? "bg-zinc-100 text-black hover:bg-white"
              : "cursor-not-allowed bg-zinc-700 text-zinc-500"
          }`}
        >
          <ArrowUp size={18} />
        </button>
      </form>
    </div>
  );
}

export default ChatInput;