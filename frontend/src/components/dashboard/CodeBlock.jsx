import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

function CodeBlock({ language, children }) {
  const [copied, setCopied] = useState(false);

  const copyCode = async () => {
    await navigator.clipboard.writeText(children);

    setCopied(true);

    setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  return (
    <div className="my-5 overflow-hidden rounded-2xl border border-zinc-700 shadow-lg">
      <div className="flex items-center justify-between border-b border-zinc-700 bg-zinc-900 px-4 py-3">
        <span className="rounded-md bg-zinc-800 px-3 py-1 text-xs font-medium uppercase tracking-wide text-zinc-300">
          {language}
        </span>

        <button
          onClick={copyCode}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-300 transition-all duration-200 hover:bg-zinc-800 hover:text-white"
        >
          {copied ? (
            <>
              <Check size={16} className="text-green-400" />
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

      <SyntaxHighlighter
        language={language}
        style={oneDark}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: 0,
          padding: "20px",
          background: "#111827",
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
}

export default CodeBlock;