const RESEARCH_ROUTES = new Set(["rag", "web", "hybrid"]);

export function isResearchRoute(route) {
  return RESEARCH_ROUTES.has(String(route || "").toLowerCase());
}
