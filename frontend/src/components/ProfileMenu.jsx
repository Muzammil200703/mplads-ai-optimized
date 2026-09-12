import { useEffect, useRef, useState } from "react"
import { useAuth } from "../context/AuthContext"

/* ═══════════════════════════════════════════════════════════
   Profile menu for the TopBar — shows the signed-in user's
   name/email/role and the sign-out action.
   ═══════════════════════════════════════════════════════════ */

const ROLE_LABEL = {
  public: "Public user",
  analyst: "Analyst",
  auditor: "Auditor",
  admin: "Administrator",
}

const ROLE_BADGE = {
  public: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
  analyst: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  auditor: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  admin: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
}

export default function ProfileMenu({ onNavigate }) {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [])

  if (!user) {
    return (
      <button
        onClick={() => onNavigate && onNavigate("Sign in")}
        className="flex h-10 shrink-0 items-center gap-2 rounded-lg bg-[#031632] px-3 text-sm font-bold text-white transition hover:bg-[#0a2450] dark:bg-blue-600 dark:hover:bg-blue-500"
        aria-label="Sign in"
      >
        <span>👤</span>
        <span className="hidden sm:inline">Sign in</span>
      </button>
    )
  }

  const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase()

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 items-center gap-2 rounded-lg px-2 transition hover:bg-[#eef1f8] dark:hover:bg-[#1f2937]"
        aria-label="Profile menu"
        aria-expanded={open}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#1a2b48] text-sm font-bold text-white dark:bg-[#243b5a]">
          {initial}
        </span>
        <span className="hidden max-w-[140px] truncate text-sm font-semibold text-[#151c27] dark:text-[#f3f4f6] lg:inline">
          {user.name}
        </span>
        <span className="text-[0.625rem] text-[#44474d] dark:text-[#9ca3af]">▾</span>
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-50 w-72 overflow-hidden rounded-xl border border-[#c5c6ce] bg-white shadow-lg dark:border-[#374151] dark:bg-[#111827]">
          <div className="border-b border-[#c5c6ce] px-4 py-3 dark:border-[#374151]">
            <p className="truncate text-sm font-bold text-[#031632] dark:text-[#f3f4f6]">{user.name}</p>
            <p className="truncate text-xs text-[#44474d] dark:text-[#9ca3af]">{user.email}</p>
            <span className={`mt-2 inline-block rounded px-2 py-0.5 text-[0.6875rem] font-bold ${ROLE_BADGE[user.role] || ROLE_BADGE.public}`}>
              {ROLE_LABEL[user.role] || user.role}
            </span>
          </div>
          <div className="px-4 py-2 text-xs text-[#44474d] dark:text-[#9ca3af]">
            <p className="font-semibold uppercase tracking-wider">Workspace</p>
            <div className="mt-1 space-y-1">
              {[
                { label: "Saved Projects", page: "Saved Projects", minRole: "analyst" },
                { label: "My Investigations", page: "My Investigations", minRole: "analyst" },
                { label: "My Audit Cases", page: "My Audit Cases", minRole: "auditor" },
              ].map((it) => {
                const allowed = it.minRole === "analyst" ? true : it.minRole === "auditor" ? ["auditor", "admin"].includes(user.role) : false
                return (
                  <button
                    key={it.page}
                    disabled={!allowed}
                    onClick={() => { setOpen(false); onNavigate && onNavigate(it.page) }}
                    className={`block w-full rounded px-2 py-1.5 text-left text-[0.8125rem] transition ${
                      allowed ? "text-[#151c27] hover:bg-[#f0f3ff] dark:text-[#f3f4f6] dark:hover:bg-[#1f2937]" : "cursor-not-allowed text-[#44474d]/50 dark:text-[#9ca3af]/50"
                    }`}
                  >
                    {it.label}{!allowed && " (auditor)"}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="border-t border-[#c5c6ce] dark:border-[#374151]">
            <button
              onClick={() => { setOpen(false); logout() }}
              className="block w-full px-4 py-3 text-left text-sm font-semibold text-red-600 transition hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/30"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
