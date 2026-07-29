import { useState } from "react";
import AuthLayout from "../../layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Divider from "../../components/ui/Divider";
import { login } from "../../services/authService";
import { Link, useNavigate } from "react-router-dom";

function Login() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: ""
  })

  const initialErrors = {
    email: "",
    password: "",
  };

  const [errors, setErrors] = useState(initialErrors);


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

    setErrors({
      email: "",
      password: "",
    });

    if (!formData.email.trim()) {
      setErrors({
        email: "Email is required",
        password: "",
      });
      return;
    }

    if (!formData.password.trim()) {
      setErrors({
        email: "",
        password: "Password is required",
      });
      return;
    }

    console.log("Form Submitted ✅");
    try {
      setLoading(true);

      const data = await login(formData);

      localStorage.setItem("token", data.access_token);

      console.log("Login Successful ✅");

      navigate("/dashboard");

    } catch (error) {

      const message =
        error.response?.data?.detail ||
        "Something went wrong. Please try again.";

      setErrors((prev) => ({
        ...prev,
        password: message,
      }));

    } finally {

      setLoading(false);

    }
  };

  return (
    <AuthLayout>
      <Card>
        <div className="mb-10 text-center">
          <h1 className="text-5xl font-semibold tracking-tight text-white">
            Sign in
          </h1>

          <p className="mt-3 text-base text-zinc-400">
            Continue to AskLaw
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-1">
          <Input
            label="Email"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="Enter your email"
          />

          {errors.email && (
            <p className="text-sm text-red-500 mt-2">
              {errors.email}
            </p>
          )}

          <Input
            label="Password"
            name="password"
            type="password"
            value={formData.password}
            onChange={handleChange}
            placeholder="Enter your password"
          />


          {errors.password && (
            <p className="text-sm text-red-500 mt-2">
              {errors.password}
            </p>
          )}
          <div className="pt-3">
            <Button type="submit">
              Continue
            </Button>
          </div>
        </form>

        <Divider />

        <p className="text-center text-sm text-zinc-400">
          Don't have an account?{" "}
          <Link
            to="/signup"
            className="font-medium text-white hover:underline"
          >
            Create account
          </Link>
        </p>
      </Card>
    </AuthLayout>
  );
}

export default Login;