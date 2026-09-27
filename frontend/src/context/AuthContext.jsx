import { createContext, useContext, useState, useEffect } from 'react'
import client from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('access_token'))

  // On a fresh page load, the access token might still be valid (or
  // refreshable) even though `user` starts out null — without this, the
  // profile avatar/name would just be blank until the next login.
  useEffect(() => {
    if (isAuthenticated && !user) {
      client.get('/auth/me/').then(({ data }) => setUser(data)).catch(() => {})
    }
  }, [isAuthenticated])

  const login = async (username, password) => {
    const { data } = await client.post('/auth/login/', { username, password })
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    setIsAuthenticated(true)
    const me = await client.get('/auth/me/')
    setUser(me.data)
  }

  const register = async (username, email, password) => {
    await client.post('/auth/register/', { username, email, password })
    await login(username, password)
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setIsAuthenticated(false)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, login, register, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
