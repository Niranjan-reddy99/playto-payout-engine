import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001';
const AUTH_PATH = '/auth/login/';
let csrfToken = '';

// withCredentials: true tells the browser to include the session cookie on
// every request. Without this, Django cannot identify who is logged in.
export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// On Vercel -> Railway, the browser keeps API cookies on the API domain, so
// the frontend cannot reliably read `csrftoken` from document.cookie.
// Instead we fetch the token once and keep it in memory for future requests.
export async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) {
    return csrfToken;
  }

  const response = await axios.get<{ csrfToken: string }>(`${API_BASE}/api/v1${AUTH_PATH}`, {
    withCredentials: true,
  });
  csrfToken = response.data.csrfToken;
  return csrfToken;
}

export function setCsrfToken(token?: string) {
  csrfToken = token || '';
}

// Intercept every outgoing request. For anything that changes data,
// attach the CSRF token as a header so Django allows it through.
// GET/HEAD/OPTIONS/TRACE are read-only so they don't need it.
apiClient.interceptors.request.use(async (config) => {
  const method = config.method?.toUpperCase();
  if (method && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const token = await ensureCsrfToken();
    config.headers['X-CSRFToken'] = token;
  }
  return config;
});
