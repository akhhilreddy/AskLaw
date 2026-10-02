import { useState } from "react";
import { Fingerprint } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  authenticateWithPasskey,
  isPasskeySupported,
  passkeyErrorMessage,
} from "../../services/passkeyService";


export default function PasskeyAuthButton() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!isPasskeySupported()) return null;

  const handleSignIn = async () => {
    setLoading(true);
    setError("");
    try {
      const session = await authenticateWithPasskey();
      localStorage.setItem("token", session.access_token);
      navigate("/dashboard");
    } catch (requestError) {
      setError(
        passkeyErrorMessage(requestError, "Passkey sign-in failed. Please try again.")
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="oauth-section">
      <div className="auth-divider"><span>or</span></div>
      <button
        className="passkey-auth-button"
        type="button"
        onClick={handleSignIn}
        disabled={loading}
      >
        <Fingerprint size={19} aria-hidden="true" />
        {loading ? "Waiting for Touch ID…" : "Sign in with Touch ID or Face ID"}
      </button>
      {error && <p className="field-error passkey-auth-error" role="alert">{error}</p>}
    </div>
  );
}
