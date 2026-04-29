import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// withCredentials: true tells the browser to include the session cookie on
// every request. Without this, Django cannot identify who is logged in.
export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// Django requires a CSRF token on all state-changing requests (POST, PUT, DELETE).
// When we log in, Django sets a csrftoken cookie. This function reads it.
function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

// Intercept every outgoing request. For anything that changes data,
// attach the CSRF token as a header so Django allows it through.
// GET/HEAD/OPTIONS/TRACE are read-only so they don't need it.
apiClient.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase();
  if (method && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    config.headers['X-CSRFToken'] = getCsrfToken();
  }
  return config;
});
