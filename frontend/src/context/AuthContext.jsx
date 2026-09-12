import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import { fetchMe, getToken, login as apiLogin, signup as apiSignup, logout as apiLogout } from "../services/api"

const AuthContext = createContext(null)

// Role hierarchy for UI gating — mirrors backend auth.ROLE_RANK
const ROLE_RANK = { public: 0, analyst: 1, auditor: 2, admin: 3 }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true) // session restore on first load

  // Restore a persistent session from the stored token
  useEffect(() => {
    let alive = true
    const restore = async () => {
      if (!getToken()) { setLoading(false); return }
      try {
        const me = await fetchMe()
        if (alive) setUser(me)
      } catch {
        // token invalid/expired — api layer already cleared it
        if (alive) setUser(null)
      } finally {
        if (alive) setLoading(false)
      }
    }
    restore()
    // React to session expiry triggered by any API call
    const onExpired = () => setUser(null)
    window.addEventListener("auth-expired", onExpired)
    return () => { alive = false; window.removeEventListener("auth-expired", onExpired) }
  }, [])

  const login = useCallback(async (email, password) => {
    const data = await apiLogin(email, password)
    setUser(data.user)
    return data.user
  }, [])

  const signup = useCallback(async (payload) => {
    const data = await apiSignup(payload)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    apiLogout()
    setUser(null)
  }, [])

  const hasRole = useCallback(
    (minimum) => {
      if (!user) return false
      return (ROLE_RANK[user.role] ?? 0) >= (ROLE_RANK[minimum] ?? 99)
    },
    [user]
  )

  const value = useMemo(
    () => ({ user, loading, login, signup, logout, hasRole }),
    [user, loading, login, signup, logout, hasRole]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>")
  return ctx
}
