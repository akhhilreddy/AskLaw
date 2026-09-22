import axios from "axios";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

// Only attach the access token to authenticated requests.
// Login/signup/refresh must be allowed to run without an old token.
api.interceptors.request.use(
  (config) => {
    const isAuthRequest =
      config.url === "/auth/login" ||
      config.url === "/auth/signup" ||
      config.url === "/auth/refresh";

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
    const isAuthRequest =
      originalRequest.url === "/auth/login" ||
      originalRequest.url === "/auth/signup" ||
      originalRequest.url === "/auth/refresh";

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthRequest
    ) {
      originalRequest._retry = true;

      try {
        // Refresh using a clean request that does not go through
        // the authentication interceptor again.
        const refreshResponse = await axios.post(
          `${API_BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true }
        );

        const newToken = refreshResponse.data.access_token;

        localStorage.setItem("token", newToken);

        originalRequest.headers.Authorization = `Bearer ${newToken}`;

        return api(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
