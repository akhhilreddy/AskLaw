import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getCurrentUser } from "../services/authService";
import { clearSession, isTerminalRefreshFailure } from "../services/api";

function ProtectedRoute({ children }) {
  const location = useLocation();
  const [status, setStatus] = useState("checking");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;

    getCurrentUser()
      .then(() => {
        if (active) setStatus("authenticated");
      })
      .catch((error) => {
        if (!active) return;

        if (isTerminalRefreshFailure(error)) {
          clearSession();
          setStatus("unauthenticated");
        } else {
          setStatus("unavailable");
        }
      });

    return () => {
      active = false;
    };
  }, [retryCount]);

  if (status === "checking") {
    return (
      <div className="session-state" role="status">
        Restoring your session…
      </div>
    );
  }

  if (status === "unavailable") {
    return (
      <div className="session-state" role="alert">
        <p>AskLAW could not verify your session. Check your connection.</p>
        <button
          type="button"
          onClick={() => {
            setStatus("checking");
            setRetryCount((count) => count + 1);
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children;
}

export default ProtectedRoute;
