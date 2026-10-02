import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import { requestPasswordReset } from "../../services/authService";

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (!email.trim()) {
      setError("Email is required");
      return;
    }
    try {
      setLoading(true);
      await requestPasswordReset(email);
      navigate("/reset-password", { state: { email } });
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The reset request could not be completed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <Card>
        <span className="eyebrow">Account recovery</span>
        <h1>Forgot password?</h1>
        <p>Enter your email and we will send a one-time reset code.</p>
        <form onSubmit={submit} aria-busy={loading}>
          <Input label="Email address" name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" error={error} autoComplete="email"/>
          <Button type="submit" disabled={loading}>{loading ? "Sending code…" : "Send reset code"}</Button>
        </form>
        <div className="auth-switch"><Link className="text-link" to="/login">Back to sign in</Link></div>
      </Card>
    </AuthLayout>
  );
}
