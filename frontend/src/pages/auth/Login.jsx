import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import { login } from "../../services/authService";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState({ email: "", password: "" });
  const [needsVerification, setNeedsVerification] = useState(false);

  const handleChange = (event) => {
    setFormData((previous) => ({
      ...previous,
      [event.target.name]: event.target.value,
    }));
    setErrors((previous) => ({ ...previous, [event.target.name]: "" }));
    setNeedsVerification(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrors({ email: "", password: "" });
    setNeedsVerification(false);
    if (!formData.email.trim()) {
      setErrors({ email: "Email is required", password: "" });
      return;
    }
    if (!formData.password.trim()) {
      setErrors({ email: "", password: "Password is required" });
      return;
    }

    try {
      setLoading(true);
      const data = await login(formData);
      localStorage.setItem("token", data.access_token);
      navigate("/dashboard");
    } catch (error) {
      const detail = error.response?.data?.detail || "Something went wrong. Please try again.";
      setErrors((previous) => ({ ...previous, password: detail }));
      setNeedsVerification(error.response?.status === 403);
    } finally {
      setLoading(false);
    }
  };

  const statusMessage = location.state?.emailVerified
    ? "Email verified. You can now sign in."
    : location.state?.passwordReset
      ? "Password updated. Sign in with your new password."
      : null;

  return (
    <AuthLayout>
      <Card>
        <span className="eyebrow">Welcome back</span>
        <h1>Sign in</h1>
        <p>Continue your legal research.</p>
        {statusMessage && <p className="auth-status" role="status">{statusMessage}</p>}
        <form onSubmit={handleSubmit} aria-busy={loading}>
          <Input label="Email address" name="email" type="email" value={formData.email} onChange={handleChange} placeholder="you@example.com" error={errors.email}/>
          <Input label="Password" name="password" type="password" value={formData.password} onChange={handleChange} placeholder="Enter your password" error={errors.password}/>
          <div className="auth-inline-action">
            <Link className="text-link" to="/forgot-password">Forgot password?</Link>
          </div>
          {needsVerification && (
            <p className="auth-help">Have a verification code? <Link className="text-link" to="/verify-email" state={{ email: formData.email }}>Verify email</Link></p>
          )}
          <Button type="submit" disabled={loading}>{loading ? "Signing in…" : "Sign in"}</Button>
        </form>
        <div className="auth-switch">New to AskLAW? <Link className="text-link" to="/signup">Create an account</Link></div>
      </Card>
    </AuthLayout>
  );
}
