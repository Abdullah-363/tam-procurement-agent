import { useEffect, useState } from 'react'
import { api } from './api'

// Chat state lives above the pages, so switching tabs never loses it.
// It is also saved in the browser, so a page refresh keeps the conversation.
const KEY = 'tam-chat-v1'

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null } catch { return null }
}
const fresh = () => ({ messages: [], session: `req-${Date.now()}`, lastTrace: null })

export function useChat(onChange) {
  const [chat, setChat] = useState(() => load() || fresh())
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(chat)) } catch { /* storage unavailable: keep in memory */ }
  }, [chat])

  async function send(text) {
    const msg = text.trim()
    if (!msg || busy) return
    const session = chat.session
    setChat((c) => ({ ...c, messages: [...c.messages, { role: 'user', text: msg }], lastTrace: null }))
    setBusy(true)
    try {
      const r = await api.chat(msg, session)
      setChat((c) => c.session !== session ? c : ({
        ...c,
        messages: [...c.messages, { role: 'agent', text: r.reply, prs: r.prs }],
        lastTrace: r.trace,
      }))
      onChange()
    } catch (e) {
      setChat((c) => c.session !== session ? c : ({ ...c, messages: [...c.messages, { role: 'error', text: e.message }] }))
    } finally {
      setBusy(false)
    }
  }

  // New conversation: new session id, so the agent's memory starts fresh too.
  const clear = () => setChat(fresh())

  return { ...chat, busy, send, clear }
}
