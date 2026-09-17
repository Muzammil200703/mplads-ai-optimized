import { useEffect, useRef, useState } from "react"
import { useAuth } from "../context/AuthContext"
import { askAssistant, getAssistantSuggestions, getAssistantContextHelp } from "../services/api"

/* ═══════════════════════════════════════════════════════════════════
   MPLADS AI ASSISTANT — universal role-aware widget (floating panel)
   One assistant for every role: general MPLADS help + app guidance +
   role-gated data answers. Role enforcement lives on the server; the
   widget only controls which starter suggestions it shows.
   ═══════════════════════════════════════════════════════════════════ */

const ROLE_SUGGESTIONS = {
  guest: [
    "What is MPLADS?",
    "What is the purpose of this website?",
    "How does Ground Verification work?",
    "How do I search for a project?",
  ],
  citizen: [
    "How do I submit project evidence?",
    "What happens after I upload a photo?",
    "What is a risk score?",
    "How many projects are in the portfolio?",
  ],
  field_verifier: [
    "Show my submissions",
    "How does verification work?",
    "What does a risk score mean?",
    "Who verifies citizen evidence?",
  ],
  district_authority: [
    "Show my pending inquiries",
    "How do I respond to an inquiry?",
    "What is an inquiry?",
    "How do I search for a project?",
  ],
  analyst: [
    "Which states have the most projects?",
    "Which projects have high risk?",
    "How many projects are in Karnataka?",
    "What is a risk score?",
  ],
  auditor: [
    "What should I investigate today?",
    "Which projects have high risk?",
    "Find unusual spending.",
    "What does P1 mean?",
  ],
  admin: [
    "What should I investigate today?",
    "Which projects have high risk?",
    "How does the inquiry workflow work?",
    "Find unusual spending.",
  ],
}

/** Renders **bold**, bullet lines and plain text from the engine's markdown-lite answers. */
function AnswerBody({ text }) {
  const lines = String(text || "").split("\n")
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />
        const bolded = line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
          part.startsWith("**") && part.endsWith("**")
            ? <strong key={j} className="font-bold">{part.slice(2, -2)}</strong>
            : part
        )
        if (line.trim().startsWith("•")) {
          return <p key={i} className="pl-2 text-[0.8125rem] leading-snug">{bolded}</p>
        }
        return <p key={i} className="text-[0.8125rem] leading-snug">{bolded}</p>
      })}
    </div>
  )
}

export default function AssistantWidget({ currentPage, contextProjectId, onNavigate, onOpenProject }) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([]) // {role: 'user'|'assistant', text, actions?}
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [contextHelp, setContextHelp] = useState(null) // page blurb for the 'About this page' chip
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  // Stable per-conversation session id — lets the server resolve pronoun
  // follow-ups ("why is it risky?" → "open it") to the last-discussed project.
  const sessionRef = useRef(null)
  // Last project the conversation produced (server also remembers it; this
  // mirrors it client-side so the header can show the active context).
  const [lastProjectId, setLastProjectId] = useState(null)

  const roleKey = !user ? "guest" : (user.role in ROLE_SUGGESTIONS ? user.role : "guest")

  // Fresh conversation per opened session; suggestions follow role + page.
  useEffect(() => {
    if (open) {
      setMessages([])
      setSuggestions(ROLE_SUGGESTIONS[roleKey] || ROLE_SUGGESTIONS.guest)
      setContextHelp(null)
      sessionRef.current = `asst-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      setLastProjectId(contextProjectId || null)
      setTimeout(() => inputRef.current?.focus(), 100)
      // Page-aware suggestions + context blurb, best-effort (falls back to
      // the role defaults above if the network/backend is unavailable).
      const page = contextProjectId ? `project:${contextProjectId}` : currentPage
      if (page) {
        getAssistantSuggestions(page)
          .then((d) => {
            if (d?.general?.length) setSuggestions(d.general.slice(0, 5))
          })
          .catch(() => {})
        if (!page.startsWith("project:")) {
          getAssistantContextHelp(page)
            .then((d) => { if (d?.help) setContextHelp(d.help) })
            .catch(() => {})
        } else {
          setContextHelp(null)
        }
      }
    }
  }, [open, roleKey, currentPage, contextProjectId])

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, busy])

  const send = async (questionRaw) => {
    const question = String(questionRaw || input).trim()
    if (!question || busy) return
    setInput("")
    setSuggestions([])
    setMessages((m) => [...m, { role: "user", text: question }])
    setBusy(true)
    try {
      const page = contextProjectId ? `project:${contextProjectId}` : currentPage
      const res = await askAssistant(question, page, sessionRef.current)
      if (res.project_id) setLastProjectId(res.project_id)
      setMessages((m) => [...m, { role: "assistant", text: res.answer, actions: res.actions || [] }])
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: "The assistant is temporarily unavailable. Please try again in a moment." }])
    } finally {
      setBusy(false)
    }
  }

  const runAction = (a) => {
    if (a.action === "open_project" && onOpenProject) {
      onOpenProject(parseInt(a.target, 10))
      setOpen(false)
    } else if (a.action === "navigate" && onNavigate) {
      onNavigate(a.target)
      setOpen(false)
    }
  }

  return (
    <>
      {/* Launcher */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="MPLADS AI Assistant"
        title="MPLADS AI Assistant"
        className="fixed bottom-5 right-5 z-[70] flex h-13 w-13 items-center justify-center rounded-full bg-[#031632] text-xl text-white shadow-soft transition-transform duration-200 hover:scale-105 hover:bg-[#0a2545] active:scale-95 dark:bg-blue-600 dark:hover:bg-blue-500"
        style={{ height: 52, width: 52 }}
      >
        {open ? "✕" : "✦"}
      </button>

      {/* Panel */}
      {open && (
        <div className="pop-in-up fixed bottom-20 right-5 z-[70] flex h-[520px] max-h-[calc(100vh-6rem)] w-[380px] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-2xl border border-[#dcdde4] bg-white shadow-soft-lg dark:border-[#2e2e33] dark:bg-[#0a0a0c]" style={{ transformOrigin: "bottom right" }}>
          {/* Header */}
          <div className="flex flex-none items-center gap-2.5 border-b border-[#dcdde4] bg-[#f9f9ff] px-5 py-4 dark:border-[#2e2e33] dark:bg-[#0d0d10]">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#031632] text-sm text-white dark:bg-blue-600">✦</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-[#031632] dark:text-[#f3f4f6]">MPLADS AI Assistant</p>
              <p className="text-[0.6875rem] text-[#44474d] dark:text-[#9ca3af]">
                {lastProjectId
                  ? `Discussing project #${lastProjectId}`
                  : user
                    ? `For: ${user.name.split(" ")[0]} (${user.role.replace("_", " ")})`
                    : "Public help — sign in for more"}
              </p>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-4 py-4">
            {messages.length === 0 && (
              <div className="rounded-xl bg-[#f0f3ff] p-4 text-[0.8125rem] leading-snug text-[#031632] dark:bg-[#17181c] dark:text-[#f3f4f6]">
                Namaste 🙏 I can answer questions about MPLADS, guide you through this portal, and — depending
                on your role — pull up live project, risk, vendor and verification data. All answers come from
                real portal data; nothing is invented.
              </div>
            )}
            {messages.length === 0 && contextHelp && (
              <button
                onClick={() => send("What does this page show?")}
                className="w-full rounded-xl border border-[#dcdde4] bg-white p-3 text-left transition hover:bg-[#f0f3ff] dark:border-[#2e2e33] dark:bg-[#0a0a0c] dark:hover:bg-[#17181c]"
              >
                <p className="text-[0.6875rem] font-bold uppercase tracking-wide text-[#44474d] dark:text-[#9ca3af]">
                  📍 About this page
                </p>
                <p className="mt-1 line-clamp-2 text-[0.75rem] leading-snug text-[#151c27] dark:text-gray-100">
                  {contextHelp}
                </p>
              </button>
            )}
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <p className="rise-in max-w-[85%] rounded-2xl rounded-br-md bg-[#031632] px-3.5 py-2.5 text-[0.8125rem] text-white dark:bg-blue-600">
                    {m.text}
                  </p>
                </div>
              ) : (
                <div key={i} className="flex justify-start">
                  <div className="rise-in max-w-[92%] rounded-2xl rounded-bl-md border border-[#dcdde4] bg-[#f9f9ff] px-3.5 py-2.5 text-[#151c27] dark:border-[#2e2e33] dark:bg-[#17181c] dark:text-gray-100">
                    <AnswerBody text={m.text} />
                    {m.actions?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5 border-t border-[#dcdde4] pt-2 dark:border-[#2e2e33]">
                        {m.actions.map((a, j) => (
                          <button
                            key={j}
                            onClick={() => runAction(a)}
                            className="rounded-full bg-[#031632] px-2.5 py-1 text-[0.6875rem] font-bold text-white transition hover:bg-[#0a2545] dark:bg-blue-600 dark:hover:bg-blue-500"
                          >
                            {a.action === "open_project" ? "🗂 " : "→ "}{a.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            )}
            {busy && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-2xl border border-[#dcdde4] bg-[#f9f9ff] px-3 py-2.5 dark:border-[#2e2e33] dark:bg-[#17181c]">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#031632] dark:bg-blue-400" style={{ animationDelay: "0ms" }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#031632] dark:bg-blue-400" style={{ animationDelay: "120ms" }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#031632] dark:bg-blue-400" style={{ animationDelay: "240ms" }} />
                </div>
              </div>
            )}
          </div>

          {/* Suggestions */}
          {suggestions.length > 0 && !busy && (
            <div className="flex flex-none flex-wrap gap-1.5 border-t border-[#dcdde4] px-3 pt-2.5 dark:border-[#2e2e33]">
              {suggestions.slice(0, 5).map((s, i) => (
                <button
                  key={`${i}-${s}`}
                  onClick={() => send(s)}
                  className="rounded-full border border-[#dcdde4] bg-white px-2.5 py-1 text-[0.6875rem] font-semibold text-[#031632] transition hover:bg-[#f0f3ff] dark:border-[#2e2e33] dark:bg-[#0a0a0c] dark:text-[#f3f4f6] dark:hover:bg-[#17181c]"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="flex flex-none items-center gap-2 p-3">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask about MPLADS, projects, evidence…"
              maxLength={500}
              className="min-w-0 flex-1 rounded-full border border-[#dcdde4] bg-white px-3.5 py-2 text-[0.8125rem] outline-none focus:border-[#031632] dark:border-[#2e2e33] dark:bg-[#17181c] dark:text-gray-100 dark:focus:border-blue-500"
            />
            <button
              onClick={() => send()}
              disabled={busy || !input.trim()}
              aria-label="Send"
              className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-[#031632] text-white transition hover:bg-[#0a2545] disabled:opacity-40 dark:bg-blue-600 dark:hover:bg-blue-500"
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </>
  )
}
