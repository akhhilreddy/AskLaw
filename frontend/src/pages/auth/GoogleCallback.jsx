import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import { exchangeGoogleCode } from "../../services/authService";

export default function GoogleCallback() {
  const navigate = useNavigate();
  const started = useRef(false);
  const [{ code, callbackError }] = useState(() => {
    const parameters = new URLSearchParams(window.location.search);
    const authorizationCode = parameters.get("code");

    return {
      code: authorizationCode,
      callbackError: !authorizationCode || parameters.has("error"),
    };
  });
  const [error, setError] = useState(
    callbackError ? "Google sign-in could not be completed. Please try again." : "",
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    if (callbackError) return;

    exchangeGoogleCode(code)
      .then((data) => {
        if (!data?.access_token) {
          throw new Error("Missing access token");
        }
        localStorage.setItem("token", data.access_token);
        navigate("/dashboard", { replace: true });
      })
      .catch((requestError) => {
        setError(
          requestError.response?.data?.detail ||
          "Google sign-in could not be completed. Please try again.",
        );
      });
  }, [callbackError, code, navigate]);

  return (
    <AuthLayout>
      <Card>
        <span className="eyebrow">Secure sign in</span>
        <h1>{error ? "Sign-in failed" : "Signing you in…"}</h1>
        <p>{error || "AskLAW is securely completing your Google sign-in."}</p>
        {error && <div className="auth-switch"><Link className="text-link" to="/login">Return to sign in</Link></div>}
      </Card>
    </AuthLayout>
  );
}
