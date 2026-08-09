import { useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";

function ChatInput({
  onSendMessage,
  onStopStreaming,
  isStreaming,
}) {
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
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      !isStreaming
    ) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="border-t border-[#2A2A2A] bg-[#1A1A1A] px-8 py-4">
      <form
  onSubmit={handleSubmit}
  className="mx-auto flex max-w-5xl items-center gap-4 rounded-3xl border border-[#303030] bg-[#242424] px-5 py-3"
>
        <textarea
          ref={textareaRef}
          rows={1}
          value={message}
          placeholder="Ask a legal question..."
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          className="max-h-48 flex-1 resize-none overflow-y-auto bg-transparent text-zinc-100 outline-none placeholder:text-zinc-500 disabled:cursor-not-allowed"
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onStopStreaming}
            className="flex h-11 w-11 items-center justify-center rounded-full bg-red-500 text-white transition hover:bg-red-600"
          >
            <Square
              size={16}
              fill="currentColor"
            />
          </button>
        ) : (
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
        )}
      </form>

      {/* Legal Disclaimer */}
      <p className="mx-auto mt-3 max-w-4xl px-4 text-center text-[15px] leading-4 text-zinc-600">
        AskLaw can make mistakes. Responses are for educational and
        informational purposes only and do not constitute legal advice
        or create an attorney-client relationship.
      </p>
    </div>
  );
}

export default ChatInput;