import { Link } from "react-router-dom";

import AuthLayout from "../../components/layout/AuthLayout";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import Divider from "../../components/ui/Divider";

function Signup() {
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

        <form className="space-y-1">
          <Input
            label="Full name"
            name="name"
            placeholder="Enter your full name"
          />

          <Input
            label="Email"
            name="email"
            type="email"
            placeholder="Enter your email"
          />

          <Input
            label="Password"
            name="password"
            type="password"
            placeholder="Create a password"
          />

          <div className="pt-3">
            <Button>
              Continue
            </Button>
          </div>
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