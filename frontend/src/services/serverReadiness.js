// The health probe never attaches credentials or changes API/session handling.
export const READINESS_TIMEOUT_MS = 100000;

export async function checkServerReadiness(url, { onSlow, signal, fetcher = fetch, delay = 3000 }) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const deadline = setTimeout(abort, READINESS_TIMEOUT_MS);
  const timer = setTimeout(onSlow, delay);
  try {
    const response = await fetcher(`${url}/health`, { signal: controller.signal, credentials: "omit" });
    if (!response.ok) throw new Error("Health check failed");
    const body = await response.json();
    if (body.status !== "healthy") throw new Error("API is not ready");
  } finally {
    clearTimeout(timer);
    clearTimeout(deadline);
    signal?.removeEventListener("abort", abort);
  }
}
