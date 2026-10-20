const NOTICE_TEXT = {
  web_unavailable: "Web search is temporarily unavailable, try again shortly.",
  web_partial: "Some web searches were unavailable; web coverage may be incomplete.",
  rag_unavailable: "Document research is temporarily unavailable; only available web evidence was used.",
  rag_timeout: "Document research timed out; only available evidence was used.",
  rag_busy: "Document research is busy; try again shortly.",
  research_timeout: "Research timed out; try again shortly.",
};

export const noticeText = notice => NOTICE_TEXT[notice?.type] || "";
export const emptyResearchStatus = () => ({ progress: "", availability_notices: [], availability_only: false, availability_receipt: null });

export function applyResearchEvent(state, event) {
  if (event.type === "progress") {
    if (event.code === "provider_pending") return { ...state, progress: "Preparing your answer…" };
    if (event.code === "provider_retrying") return { ...state, progress: "AI service is busy; waiting to retry…" };
    if (event.code === "web_waking") return { ...state, progress: "Waking up web search…" };
    if (event.code === "research_pending") return { ...state, progress: state.progress || "Researching…" };
    if (["web_ready", "web_unavailable"].includes(event.code)) return { ...state, progress: "" };
  }
  if (event.type === "availability") {
    const items = Array.isArray(event.notices) ? event.notices : [];
    const types = [...new Set(items.filter(item => noticeText(item)).map(item => item.type))];
    return { ...state, progress: "", availability_notices: types.map(type => ({ type })),
      availability_only: event.availability_only === true,
      availability_receipt: typeof event.receipt === "string" && event.receipt.length <= 4096 ? event.receipt : null };
  }
  if (["token", "error", "done", "stop"].includes(event.type)) return { ...state, progress: "" };
  return state;
}

export function conversationHistory(messages) {
  return messages.filter(message => !message.availability_only && typeof message.content === "string" && message.content.trim()).slice(-12).map(({ role, content }) => ({ role, content }));
}

export function finishResearchMessages(messages) {
  return messages.filter(message => message.role !== "assistant" || message.content || message.availability_notices?.length)
    .map(message => ({ ...message, progress: "", isComplete: true }));
}
