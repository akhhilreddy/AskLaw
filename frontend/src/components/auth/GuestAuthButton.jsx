import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { continueAsGuest } from "../../services/authService";

export default function GuestAuthButton() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const enterDemo = async () => {
    setLoading(true);
    setError("");
    try {
      const session = await continueAsGuest();
      localStorage.setItem("token", session.access_token);
      navigate("/dashboard");
    } catch (failure) {
      setError(failure.response?.data?.detail || "Could not start the demo. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="guest-entry">
      <button type="button" className="guest-button" disabled={loading} onClick={enterDemo}>
        {loading ? "Starting demo…" : "Continue as guest"}
      </button>
      <p className="auth-help">5 questions · 1 hour · Web research only. Create an account to upload PDFs.</p>
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}
