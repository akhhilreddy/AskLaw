import { Routes, Route } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";
import Landing from "../pages/Landing";
import Login from "../pages/auth/Login";
import Signup from "../pages/auth/Signup";
import VerifyEmail from "../pages/auth/VerifyEmail";
import ForgotPassword from "../pages/auth/ForgotPassword";
import ResetPassword from "../pages/auth/ResetPassword";
import GoogleCallback from "../pages/auth/GoogleCallback";
import Dashboard from "../pages/auth/Dashboard";
import Documents from "../pages/Documents";
import Security from "../pages/Security";
export default function AppRoutes(){return <Routes><Route path="/" element={<Landing/>}/><Route path="/login" element={<Login/>}/><Route path="/signup" element={<Signup/>}/><Route path="/verify-email" element={<VerifyEmail/>}/><Route path="/forgot-password" element={<ForgotPassword/>}/><Route path="/reset-password" element={<ResetPassword/>}/><Route path="/auth/google/callback" element={<GoogleCallback/>}/><Route path="/dashboard" element={<ProtectedRoute><Dashboard/></ProtectedRoute>}/><Route path="/documents" element={<ProtectedRoute><Documents/></ProtectedRoute>}/><Route path="/security" element={<ProtectedRoute><Security/></ProtectedRoute>}/></Routes>}
