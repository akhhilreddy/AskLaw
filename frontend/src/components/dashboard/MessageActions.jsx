import { Copy, Check } from "lucide-react";
import { useState } from "react";

function MessageActions({ content }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);

    setCopied(true);

    setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  return (
    <div className="mt-3 flex items-center gap-2">
      <button
        onClick={handleCopy}
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 transition hover:bg-zinc-800 hover:text-white"
      >
        {copied ? (
          <>
            <Check
              size={16}
              className="text-green-400"
            />
            Copied
          </>
        ) : (
          <>
            <Copy size={16} />
            Copy
          </>
        )}
      </button>
    </div>
  );
}

export default MessageActions;