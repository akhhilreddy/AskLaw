import axios from "axios";

export const API_BASE_URL = (
  import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

let refreshPromise = null;
let redirectingToLogin = false;

const unauthenticatedPaths = new Set([
  "/auth/login",
  "/auth/signup",
  "/auth/refresh",
  "/auth/token",
]);

const isUnauthenticatedRequest = (url) => unauthenticatedPaths.has(url);

export const isTerminalRefreshFailure = (error) => {
  if (error?.isAuthSessionError) return true;

  return [400, 401, 403].includes(error?.response?.status);
};

export const clearSession = () => {
  localStorage.removeItem("token");
};

export const clearSessionAndRedirect = () => {
  clearSession();

  if (!redirectingToLogin && window.location.pathname !== "/login") {
    redirectingToLogin = true;
    window.location.replace("/login");
  }
};

export const refreshAccessToken = () => {
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${API_BASE_URL}/auth/refresh`, {}, { withCredentials: true })
      .then((response) => {
        const newToken = response.data?.access_token;

        if (!newToken) {
          const error = new Error("Refresh response did not contain an access token.");
          error.isAuthSessionError = true;
          throw error;
        }

        localStorage.setItem("token", newToken);
        return newToken;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
};

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

// Only attach the access token to authenticated requests.
// Login/signup/refresh must be allowed to run without an old token.
api.interceptors.request.use(
  (config) => {
    const isAuthRequest = isUnauthenticatedRequest(config.url);

    if (!isAuthRequest) {
      const token = localStorage.getItem("token");

      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }

    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,

  async (error) => {
    const originalRequest = error.config;

    if (!originalRequest) {
      return Promise.reject(error);
    }

    // Never try token refresh for auth endpoints themselves.
    const isAuthRequest = isUnauthenticatedRequest(originalRequest.url);

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthRequest
    ) {
      originalRequest._retry = true;
      let newToken;

      try {
        newToken = await refreshAccessToken();
      } catch (refreshError) {
        if (isTerminalRefreshFailure(refreshError)) {
          clearSessionAndRedirect();
        }

        return Promise.reject(refreshError);
      }

      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${newToken}`;

      return api(originalRequest);
    }

    return Promise.reject(error);
  }
);

export default api;
