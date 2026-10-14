// The health probe never attaches credentials or changes API/session handling.
export async function checkServerReadiness(url, { onSlow, signal, fetcher = fetch, delay = 3000 }) {
  const timer = setTimeout(onSlow, delay);
  try {
    const response = await fetcher(`${url}/health`, { signal, credentials: "omit" });
    if (!response.ok) throw new Error("Health check failed");
    const body = await response.json();
    if (body.status !== "healthy") throw new Error("API is not ready");
  } finally {
    clearTimeout(timer);
  }
}
