import axios from 'axios'

// In local dev, Vite doesn't have VITE_API_BASE_URL set, so this falls back
// to localhost:8000 automatically. In production (Vercel), set
// VITE_API_BASE_URL in the project's environment variables to your deployed
// Django URL — e.g. https://documind-backend.onrender.com/api — and this
// picks it up automatically at build time. Vite only exposes env vars
// prefixed with VITE_ to the browser bundle; this is required, not a style choice.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const client = axios.create({ baseURL: API_BASE_URL })

// Attach the JWT access token (if present) to every request automatically.
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// If a request comes back 401 (access token expired), try ONCE to use the
// refresh token to get a new access token, then retry the original request.
// Without this, any login session longer than the access token's lifetime
// (1 hour) starts failing on every request, even though the user is still
// legitimately logged in.
let isRefreshing = false
let pendingRequests = []

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error)
    }

    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      return Promise.reject(error)
    }

    originalRequest._retry = true

    if (isRefreshing) {
      // A refresh is already in flight — wait for it instead of firing a second one.
      return new Promise((resolve, reject) => {
        pendingRequests.push({ resolve, reject, originalRequest })
      })
    }

    isRefreshing = true
    try {
      const { data } = await axios.post(`${API_BASE_URL}/auth/refresh/`, { refresh: refreshToken })
      localStorage.setItem('access_token', data.access)

      pendingRequests.forEach(({ resolve, originalRequest: req }) => {
        req.headers.Authorization = `Bearer ${data.access}`
        resolve(client(req))
      })
      pendingRequests = []

      originalRequest.headers.Authorization = `Bearer ${data.access}`
      return client(originalRequest)
    } catch (refreshError) {
      // Refresh token itself is expired/invalid — the user genuinely needs to log in again.
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  }
)

export default client
