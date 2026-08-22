import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import CodeBlock from "./CodeBlock";
import MessageActions from "./MessageActions";


function ChatMessage({ message }) {
  const isUser = message.role === "user";


  // =====================================================
  // PREPARE SOURCES
  // =====================================================

  const getUniqueSources = () => {
    if (
      !message.sources ||
      message.sources.length === 0
    ) {
      return [];
    }


    // ---------------------------------------------------
    // Find sources that have page numbers
    // ---------------------------------------------------

    const sourcesWithPages =
      message.sources.filter(
        (source) =>
          source.page_number !== null &&
          source.page_number !== undefined
      );


    // ---------------------------------------------------
    // If at least one source has a page number,
    // only show those sources.
    // Otherwise show all sources.
    // ---------------------------------------------------

    const sourcesToShow =
      sourcesWithPages.length > 0
        ? sourcesWithPages
        : message.sources;


    // ---------------------------------------------------
    // Remove duplicates
    // ---------------------------------------------------

    const uniqueSources = Array.from(
      new Map(
        sourcesToShow.map(
          (source) => [
            `${source.document_id}-${source.page_number}`,
            source,
          ]
        )
      ).values()
    );


    return uniqueSources;
  };


  const uniqueSources =
    getUniqueSources();


  // =====================================================
  // COMPONENT
  // =====================================================

  return (
    <div
      className={`flex ${
        isUser
          ? "justify-end"
          : "justify-start"
      }`}
    >
      <div
        className={`max-w-[75%] rounded-3xl border px-6 py-4 transition-all duration-300 ${
          isUser
            ? "border-[#3A3A3A] bg-[#2A2A2A] text-zinc-100"
            : "border-[#303030] bg-[#202020] text-zinc-100"
        }`}
      >

        {/* ============================================= */}
        {/* USER MESSAGE */}
        {/* ============================================= */}

        {isUser ? (
          <p className="whitespace-pre-wrap break-words leading-7">
            {message.content}
          </p>
        ) : (
          <>

            {/* ========================================= */}
            {/* AI RESPONSE */}
            {/* ========================================= */}

            <div className="prose prose-invert max-w-none break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({
                    className,
                    children,
                  }) {
                    const match =
                      /language-(\w+)/.exec(
                        className || ""
                      );

                    if (match) {
                      return (
                        <CodeBlock
                          language={match[1]}
                        >
                          {String(
                            children
                          ).replace(
                            /\n$/,
                            ""
                          )}
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


            {/* ========================================= */}
            {/* SOURCES */}
            {/* ========================================= */}

            {uniqueSources.length > 0 && (
              <div className="mt-5 border-t border-[#303030] pt-4">

                <p className="mb-3 text-sm font-semibold text-zinc-300">
                  Sources
                </p>

                <div className="flex flex-col gap-2">

                  {uniqueSources.map(
                    (source, index) => (
                      <div
                        key={
                          `${source.document_id}-${source.page_number}-${index}`
                        }
                        className="flex items-center justify-between rounded-xl border border-[#353535] bg-[#181818] px-4 py-3"
                      >

                        <div className="flex min-w-0 items-center gap-3">

                          <span className="text-lg">
                            📄
                          </span>

                          <span className="truncate text-sm text-zinc-300">
                            {source.filename ||
                              "Unknown document"}
                          </span>

                        </div>


                        {/* PAGE NUMBER */}

                        {source.page_number !== null &&
                          source.page_number !== undefined && (
                            <span className="ml-4 whitespace-nowrap text-xs text-zinc-500">
                              Page{" "}
                              {source.page_number}
                            </span>
                          )}

                      </div>
                    )
                  )}

                </div>

              </div>
            )}


            {/* ========================================= */}
            {/* MESSAGE ACTIONS */}
            {/* ========================================= */}

            {message.isComplete && (
              <MessageActions
                content={message.content}
              />
            )}

          </>
        )}

      </div>
    </div>
  );
}


export default ChatMessage;