import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import { resetPassword } from "../../services/authService";

export default function ResetPassword() {
  const location = useLocation();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    email: location.state?.email || "",
    code: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const change = (event) => {
    const { name, value } = event.target;
    setFormData((previous) => ({
      ...previous,
      [name]: name === "code" ? value.replace(/\D/g, "").slice(0, 6) : value,
    }));
    setError("");
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!formData.email.trim() || !/^\d{6}$/.test(formData.code)) {
      setError("Enter your email address and the six-digit reset code.");
      return;
    }
    if (formData.newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (formData.newPassword !== formData.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    try {
      setLoading(true);
      await resetPassword({
        email: formData.email,
        code: formData.code,
        new_password: formData.newPassword,
      });
      navigate("/login", { state: { passwordReset: true } });
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The password could not be reset.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <Card>
        <span className="eyebrow">Account recovery</span>
        <h1>Reset password</h1>
        <p>Use the six-digit email code and choose a new password.</p>
        <form onSubmit={submit} aria-busy={loading}>
          <Input label="Email address" name="email" type="email" value={formData.email} onChange={change} placeholder="you@example.com" autoComplete="email"/>
          <Input label="Reset code" name="code" value={formData.code} onChange={change} placeholder="000000" inputMode="numeric" autoComplete="one-time-code" maxLength={6}/>
          <Input label="New password" name="newPassword" type="password" value={formData.newPassword} onChange={change} placeholder="Create a new password" autoComplete="new-password"/>
          <Input label="Confirm password" name="confirmPassword" type="password" value={formData.confirmPassword} onChange={change} placeholder="Repeat the new password" autoComplete="new-password"/>
          {error && <p className="field-error auth-server-error" role="alert">{error}</p>}
          <Button type="submit" disabled={loading}>{loading ? "Updating password…" : "Update password"}</Button>
        </form>
        <div className="auth-switch"><Link className="text-link" to="/forgot-password">Request another code</Link></div>
      </Card>
    </AuthLayout>
  );
}
