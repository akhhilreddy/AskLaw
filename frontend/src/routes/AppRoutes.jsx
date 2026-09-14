import { Routes, Route } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";
import Landing from "../pages/Landing";
import Login from "../pages/auth/Login";
import Signup from "../pages/auth/Signup";
import Dashboard from "../pages/auth/Dashboard";
import Documents from "../pages/Documents";
export default function AppRoutes(){return <Routes><Route path="/" element={<Landing/>}/><Route path="/login" element={<Login/>}/><Route path="/signup" element={<Signup/>}/><Route path="/dashboard" element={<ProtectedRoute><Dashboard/></ProtectedRoute>}/><Route path="/documents" element={<ProtectedRoute><Documents/></ProtectedRoute>}/></Routes>}
