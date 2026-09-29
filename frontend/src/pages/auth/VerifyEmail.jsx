import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import { resendVerification, verifyEmail } from "../../services/authService";

export default function VerifyEmail() {
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState(location.state?.email || "");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (!email.trim() || !/^\d{6}$/.test(code)) {
      setError("Enter your email address and the six-digit code.");
      return;
    }
    try {
      setLoading(true);
      await verifyEmail({ email, code });
      navigate("/login", { state: { emailVerified: true } });
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Verification failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    setError("");
    setMessage("");
    if (!email.trim()) {
      setError("Enter your email address first.");
      return;
    }
    try {
      setResending(true);
      await resendVerification(email);
      setMessage("If this account is awaiting verification, a new code has been sent.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The code could not be resent.");
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout>
      <Card>
        <span className="eyebrow">Confirm your inbox</span>
        <h1>Verify email</h1>
        <p>Enter the six-digit code sent to your email address.</p>
        {message && <p className="auth-status" role="status">{message}</p>}
        <form onSubmit={submit} aria-busy={loading}>
          <Input label="Email address" name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email"/>
          <Input label="Verification code" name="code" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" inputMode="numeric" autoComplete="one-time-code" maxLength={6}/>
          {error && <p className="field-error auth-server-error" role="alert">{error}</p>}
          <Button type="submit" disabled={loading || resending}>{loading ? "Verifying…" : "Verify email"}</Button>
        </form>
        <button className="auth-secondary-action" type="button" onClick={resend} disabled={loading || resending}>{resending ? "Sending…" : "Send another code"}</button>
        <div className="auth-switch"><Link className="text-link" to="/login">Back to sign in</Link></div>
      </Card>
    </AuthLayout>
  );
}
