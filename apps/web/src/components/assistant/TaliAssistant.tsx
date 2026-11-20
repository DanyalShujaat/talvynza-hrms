import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, RefreshCw, Send, Sparkles, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState, type FormEvent, type PointerEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '@/lib/api'
import './tali.css'

const TaliPet = lazy(() => import('./TaliPet').then(module => ({ default: module.TaliPet })))

type LinkInfo = { path: string; label: string }
type Proposal = { id: string; description: string }
type Message = { id: number; from: 'tali' | 'you'; text: string; link?: LinkInfo | null; proposal?: Proposal | null }
type ChatResponse = { reply: string; link: LinkInfo | null; proposal: Proposal | null }
type AIStatus = { ready: boolean; provider: 'ollama' | 'groq'; message: string }

const welcome: Message = { id: 0, from: 'tali', text: "Hi, I'm Tali! Ask me about your tasks or leave, or tell me about a task you'd like to create or move." }
const topics = [
  { label: 'My tasks', question: 'What tasks do I have?' },
  { label: 'Leave balance', question: 'What is my leave balance?' },
  { label: 'Create a task', question: 'Help me create a task' },
]

export function TaliAssistant() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<Message[]>([welcome])
  const [status, setStatus] = useState<AIStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [motion, setMotion] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const pointer = useRef({ x: 0, y: 0 })
  const nextId = useRef(1)
  const input = useRef<HTMLInputElement>(null)
  const end = useRef<HTMLDivElement>(null)

  const checkStatus = async () => {
    setStatus(null)
    try { setStatus(await api<AIStatus>('/assistant/status')) }
    catch (error) { setStatus({ ready: false, provider: 'ollama', message: errorMessage(error) }) }
  }
  useEffect(() => { if (open) void checkStatus() }, [open])
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setMotion(!media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => { if (open) input.current?.focus() }, [open])
  useEffect(() => { if (open && end.current?.parentElement) end.current.parentElement.scrollTop = end.current.parentElement.scrollHeight }, [messages, open])
  useEffect(() => {
    if (!open) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])

  const addMessage = (message: Omit<Message, 'id'>) => {
    const id = nextId.current++
    setMessages(previous => [...previous, { id, ...message }])
    return id
  }
  const ask = async (question: string) => {
    const text = question.trim()
    if (!text || busy) return
    if (!status?.ready) { void checkStatus(); return }
    const history = messages.filter(message => message.id > 0).slice(-8)
      .map(message => ({ role: message.from === 'you' ? 'user' : 'assistant', content: message.text }))
    addMessage({ from: 'you', text })
    setDraft('')
    setBusy(true)
    try {
      const reply = await api<ChatResponse>('/assistant/chat', { method: 'POST', body: { message: text, history } })
      addMessage({ from: 'tali', text: reply.reply, link: reply.link, proposal: reply.proposal })
    } catch (error) { addMessage({ from: 'tali', text: errorMessage(error) }) }
    finally { setBusy(false) }
  }
  const confirm = async (message: Message) => {
    if (!message.proposal || busy) return
    setBusy(true)
    try {
      const result = await api<{ reply: string; link: LinkInfo }>('/assistant/confirm', {
        method: 'POST', body: { proposal_id: message.proposal.id },
      })
      setMessages(previous => previous.map(item => item.id === message.id
        ? { ...item, text: result.reply, link: result.link, proposal: null } : item))
      await qc.invalidateQueries()
    } catch (error) { addMessage({ from: 'tali', text: errorMessage(error) }) }
    finally { setBusy(false) }
  }
  const cancel = (id: number) => setMessages(previous => previous.map(item => item.id === id
    ? { ...item, text: "Okay, I won't make that change.", proposal: null } : item))
  const submit = (event: FormEvent) => { event.preventDefault(); void ask(draft) }
  const trackPointer = (event: PointerEvent<HTMLButtonElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    pointer.current.x = Math.max(-1, Math.min(1, (event.clientX - box.left - box.width / 2) / (box.width / 2)))
    pointer.current.y = Math.max(-1, Math.min(1, (event.clientY - box.top - box.height / 2) / (box.height / 2)))
  }

  return <div className="tali-root no-print">
    {open && <section className="tali-panel" aria-label="Chat with Tali">
      <header className="tali-panel-header">
        <span className="tali-panel-mark" aria-hidden="true">✦</span>
        <span className="tali-panel-heading"><strong>Talk to Tali</strong><small>{status?.provider === 'groq' ? 'Hosted AI' : 'Local AI'}{status?.ready ? ' · ready' : ''}</small></span>
        <button className="tali-close" type="button" onClick={() => setOpen(false)} aria-label="Close Tali"><X size={17} /></button>
      </header>
      <div className="tali-status" role="status"><span className={status?.ready ? 'tali-status-dot tali-status-ready' : 'tali-status-dot'} />{status?.message ?? 'Checking the local AI...'}{status && !status.ready && <button type="button" onClick={() => void checkStatus()} aria-label="Check AI again"><RefreshCw size={13} /></button>}</div>
      <div className="tali-messages" role="log" aria-live="polite" aria-label="Conversation">
        {messages.map(message => <div className={`tali-message tali-message-${message.from}`} key={message.id}>
          {message.from === 'tali' && <span className="tali-avatar" aria-hidden="true">✦</span>}
          <div className="tali-bubble"><p>{message.text}</p>
            {message.link && <Link to={message.link.path} onClick={() => setOpen(false)} className="tali-message-link">{message.link.label}<ArrowRight size={14} /></Link>}
            {message.proposal && <div className="tali-proposal"><strong>{message.proposal.description}</strong><div><button type="button" disabled={busy} onClick={() => void confirm(message)}>Confirm</button><button type="button" disabled={busy} onClick={() => cancel(message.id)}>Cancel</button></div></div>}
          </div>
        </div>)}
        {busy && <p className="tali-thinking" role="status">Tali is thinking...</p>}
        <div ref={end} />
      </div>
      {messages.length === 1 && <div className="tali-topics">{topics.map(topic => <button type="button" key={topic.label} disabled={!status?.ready || busy} onClick={() => void ask(topic.question)}>{topic.label}</button>)}</div>}
      <form className="tali-compose" onSubmit={submit}>
        <input ref={input} value={draft} onChange={event => setDraft(event.target.value)} maxLength={1000} disabled={!status?.ready || busy} aria-label="Ask Tali" placeholder="Ask Tali anything about your work..." />
        <button type="submit" disabled={!status?.ready || busy || !draft.trim()} aria-label="Send message"><Send size={16} /></button>
      </form>
      <p className="tali-disclosure"><Sparkles size={11} /> {status?.provider === 'groq' ? 'Limited context is sent to Groq.' : 'Conversation stays on this computer.'} Changes need confirmation.</p>
    </section>}
    <button type="button" className={`tali-pet-button${open ? ' tali-pet-open' : ''}`} onClick={() => setOpen(previous => !previous)} onPointerMove={trackPointer} onPointerEnter={() => setHovered(true)} onPointerLeave={() => { setHovered(false); pointer.current.x = 0; pointer.current.y = 0 }} aria-label={open ? 'Close Tali assistant' : 'Open Tali assistant'} aria-expanded={open} title="Meet Tali">
      {!open && <span className="tali-hello">Need a hand?</span>}
      <span className="tali-pet-stage" aria-hidden="true"><Suspense fallback={<span className="tali-loading">✦</span>}><TaliPet active={open || hovered} pointer={pointer} motion={motion} /></Suspense></span>
      <span className="tali-pet-ground" aria-hidden="true" />
      <span className="tali-pet-name">Tali <span className={`tali-online${status?.ready ? ' tali-online-ready' : ''}`} /></span>
    </button>
  </div>
}
