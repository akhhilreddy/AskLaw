import { useEffect, useState } from "react";
import { API_BASE_URL } from "../../services/api";
import { checkServerReadiness } from "../../services/serverReadiness";

export default function ServerReadiness() {
  const [status, setStatus] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    checkServerReadiness(API_BASE_URL, {
      signal: controller.signal,
      onSlow: () => { if (active) setStatus("waking"); },
    }).then(() => { if (active) setStatus(""); })
      .catch(() => { if (active) setStatus("unavailable"); });
    return () => { active = false; controller.abort(); };
  }, [attempt]);

  if (!status) return null;
  return <div className="server-readiness" role="status" aria-live="polite">
    {status === "waking" ? "Server is waking up, this can take up to 100 seconds." : <>
      Could not reach the server. Please retry. <button type="button" onClick={() => { setStatus(""); setAttempt(value => value + 1); }}>Retry</button>
    </>}
  </div>;
}
