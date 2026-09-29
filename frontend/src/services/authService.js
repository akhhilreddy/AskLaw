import api from "./api";
import { normalizeSignupError } from "./authError";

export const login = async (formData) => {
  const response = await api.post("/auth/login", formData);
  return response.data;
};

export const getCurrentUser = async () => {
    const response = await api.get("/auth/me");
    return response.data;
};

export const signup = async (formData) => {
  try {
    const response = await api.post("/auth/signup", formData);
    return response.data;
  } catch (error) {
    throw new Error(normalizeSignupError(error), { cause: error });
  }
};

export const verifyEmail = async (formData) => {
  const response = await api.post("/auth/verify-email", formData);
  return response.data;
};

export const resendVerification = async (email) => {
  const response = await api.post("/auth/resend-verification", { email });
  return response.data;
};

export const requestPasswordReset = async (email) => {
  const response = await api.post("/auth/forgot-password", { email });
  return response.data;
};

export const resetPassword = async (formData) => {
  const response = await api.post("/auth/reset-password", formData);
  return response.data;
};

export const logout = async () => {
  const response = await api.post("/auth/logout");

  localStorage.removeItem("token");

  return response.data;
};

export const getMe = async () => {
  const response = await api.get("/auth/me");
  return response.data;
};
