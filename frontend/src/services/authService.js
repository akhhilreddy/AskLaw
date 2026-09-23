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

export const logout = async () => {
  const response = await api.post("/auth/logout");

  localStorage.removeItem("token");

  return response.data;
};

export const getMe = async () => {
  const response = await api.get("/auth/me");
  return response.data;
};
