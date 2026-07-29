import { Link } from "react-router-dom";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { signup } from "../../services/authService";

import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Divider from "../../components/ui/Divider";

function Signup() {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
  });

  const [errors, setErrors] = useState({
    name: "",
    email: "",
    password: "",
  });

  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));

    setErrors((prev) => ({
      ...prev,
      [e.target.name]: "",
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const newErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = "Name is required";
    }

    if (!formData.email.trim()) {
      newErrors.email = "Email is required";
    }

    if (!formData.password.trim()) {
      newErrors.password = "Password is required";
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    try {
      setLoading(true);

      await signup(formData);

      alert("Account created successfully!");

      navigate("/login");

    } catch (error) {
      alert(error.response?.data?.detail || "Signup failed");
    } finally {
      setLoading(false);
    }
  };
  return (
    <AuthLayout>
      <Card>
        <div className="mb-10 text-center">
          <h1 className="text-5xl font-semibold tracking-tight text-white">
            Create account
          </h1>

          <p className="mt-3 text-base text-zinc-400">
            Join AskLaw
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-1">
          <Input
            label="Full name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            placeholder="Enter your full name"
            error={errors.name}
          />
          <Input
            label="Email"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="Enter your email"
            error={errors.email}
          />
          <Input
            label="Password"
            name="password"
            type="password"
            value={formData.password}
            onChange={handleChange}
            placeholder="Create a password"
            error={errors.password}
          />

          <Button type="submit" disabled={loading}>
            {loading ? "Creating Account..." : "Continue"}
          </Button>
        </form>

        <Divider />

        <p className="text-center text-sm text-zinc-400">
          Already have an account?{" "}
          <Link
            to="/login"
            className="font-medium text-white hover:underline"
          >
            Sign in
          </Link>
        </p>
      </Card>
    </AuthLayout>
  );
}

export default Signup;