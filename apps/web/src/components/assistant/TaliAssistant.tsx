import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Footprints, RefreshCw, Send, Sparkles, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type { TaliPose } from './TaliPet'
import './tali.css'

const TaliPet = lazy(() => import('./TaliPet').then(module => ({ default: module.TaliPet })))

type LinkInfo = { path: string; label: string }
type Proposal = { id: string; description: string }
type Message = { id: number; from: 'tali' | 'you'; text: string; link?: LinkInfo | null; proposal?: Proposal | null }
type ChatResponse = { reply: string; link: LinkInfo | null; proposal: Proposal | null }
type Availability = 'checking' | 'available' | 'unavailable'

const welcome: Message = { id: 0, from: 'tali', text: "How can I help? Ask about your tasks or leave balance, or get help finding a page." }
const topics = [
  { label: 'My tasks', question: 'What tasks do I have?' },
  { label: 'Leave balance', question: 'What is my leave balance?' },
  { label: 'Create a task', question: 'Help me create a task' },
]
const moves: TaliPose[] = ['walk', 'tired', 'sleep', 'slip']

export function TaliAssistant() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<Message[]>([welcome])
  const [availability, setAvailability] = useState<Availability>('checking')
  const [busy, setBusy] = useState(false)
  const [motion, setMotion] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [pose, setPose] = useState<TaliPose>('idle')
  const [moveIndex, setMoveIndex] = useState(0)
  const pointer = useRef({ x: 0, y: 0 })
  const moveTimer = useRef<number | undefined>(undefined)
  const nextId = useRef(1)
  const input = useRef<HTMLTextAreaElement>(null)
  const launcher = useRef<HTMLButtonElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const end = useRef<HTMLDivElement>(null)

  const checkStatus = async () => {
    setAvailability('checking')
    try {
      const { ready } = await api<{ ready: boolean }>('/assistant/status')
      setAvailability(ready ? 'available' : 'unavailable')
    } catch {
      setAvailability('unavailable')
    }
  }
  const close = () => {
    setOpen(false)
    requestAnimationFrame(() => launcher.current?.focus())
  }
  useEffect(() => { if (open) void checkStatus() }, [open])
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setMotion(!media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (open && motion) return
    window.clearTimeout(moveTimer.current)
    setPose('idle')
  }, [open, motion])
  useEffect(() => () => window.clearTimeout(moveTimer.current), [])
  useEffect(() => { if (open) closeButton.current?.focus() }, [open])
  useEffect(() => { if (open && end.current?.parentElement) end.current.parentElement.scrollTop = end.current.parentElement.scrollHeight }, [messages, open])
  useEffect(() => {
    if (!open) return
    const onEscape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !event.defaultPrevented) close() }
    window.addEventListener('keydown', onEscape)
    return () => window.removeEventListener('keydown', onEscape)
  }, [open])

  const addMessage = (message: Omit<Message, 'id'>) => {
    const id = nextId.current++
    setMessages(previous => [...previous, { id, ...message }])
    return id
  }
  const ask = async (question: string) => {
    const text = question.trim()
    if (!text || busy) return
    if (availability !== 'available') { void checkStatus(); return }
    const history = messages.filter(message => message.id > 0).slice(-8)
      .map(message => ({ role: message.from === 'you' ? 'user' : 'assistant', content: message.text }))
    addMessage({ from: 'you', text })
    setDraft('')
    setBusy(true)
    try {
      const reply = await api<ChatResponse>('/assistant/chat', { method: 'POST', body: { message: text, history } })
      addMessage({ from: 'tali', text: reply.reply, link: reply.link, proposal: reply.proposal })
    } catch { addMessage({ from: 'tali', text: 'I could not send that message. Please try again.' }) }
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
    } catch { addMessage({ from: 'tali', text: 'I could not apply that change. Review the request and try again.' }) }
    finally { setBusy(false) }
  }
  const cancel = (id: number) => setMessages(previous => previous.map(item => item.id === id
    ? { ...item, text: "Okay, I won't make that change.", proposal: null } : item))
  const submit = (event: FormEvent) => { event.preventDefault(); void ask(draft) }
  const playMove = () => {
    if (!motion) return
    const next = moves[moveIndex]
    setPose(next)
    setMoveIndex((moveIndex + 1) % moves.length)
    window.clearTimeout(moveTimer.current)
    moveTimer.current = window.setTimeout(() => setPose('idle'), next === 'slip' ? 5200 : 4600)
  }
  const canSend = availability === 'available' && !busy

  return <div className="tali-root no-print">
    {open && <section id="tali-panel" className="tali-panel" aria-label="Chat with Tali">
      <header className="tali-header">
        <span className="tali-mark" aria-hidden="true"><Sparkles size={19} /></span>
        <div className="tali-heading"><h2>Tali</h2><p>Workspace assistant</p></div>
        <div className="tali-character" aria-hidden="true">
          {motion && <Suspense fallback={null}><TaliPet active pointer={pointer} motion={motion} pose={pose} /></Suspense>}
        </div>
        {motion && <button className="tali-icon-button" type="button" onClick={playMove} aria-label="Play a Tali animation" title="Play an animation"><Footprints size={16} /></button>}
        <button ref={closeButton} className="tali-icon-button" type="button" onClick={close} aria-label="Close Tali"><X size={19} /></button>
      </header>

      {availability !== 'available' && <div className="tali-availability" role="status">
        <span>{availability === 'checking' ? 'Connecting…' : 'Tali is temporarily unavailable.'}</span>
        {availability === 'unavailable' && <button type="button" onClick={() => void checkStatus()}><RefreshCw size={14} />Retry</button>}
      </div>}

      <div className="tali-messages" role="log" aria-label="Conversation">
        {messages.map(message => <div className={`tali-message tali-message-${message.from}`} key={message.id}>
          {message.from === 'tali' && <span className="tali-avatar" aria-hidden="true"><Sparkles size={13} /></span>}
          <div className="tali-bubble">
            <p><span className="sr-only">{message.from === 'tali' ? 'Tali: ' : 'You: '}</span>{message.text}</p>
            {message.link && <Link to={message.link.path} onClick={() => setOpen(false)} className="tali-message-link">{message.link.label}<ArrowRight size={14} /></Link>}
            {message.proposal && <div className="tali-proposal">
              <strong>{message.proposal.description}</strong>
              <div><button type="button" disabled={busy} onClick={() => void confirm(message)}>Confirm change</button><button type="button" disabled={busy} onClick={() => cancel(message.id)}>Cancel</button></div>
            </div>}
          </div>
        </div>)}
        {messages.length === 1 && availability === 'available' && <div className="tali-topics" aria-label="Suggested questions">
          {topics.map(topic => <button type="button" key={topic.label} disabled={busy} onClick={() => void ask(topic.question)}>{topic.label}<ArrowRight size={14} /></button>)}
        </div>}
        {busy && <p className="tali-thinking" role="status">Working on it…</p>}
        <div ref={end} />
      </div>
      <div className="tali-footer">
        <form className="tali-compose" onSubmit={submit}>
          <textarea ref={input} value={draft} onChange={event => setDraft(event.target.value)} maxLength={1000}
            disabled={availability !== 'available'} rows={2} aria-label="Ask Tali" placeholder="Message Tali…"
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                if (canSend) void ask(draft)
              }
            }} />
          <button type="submit" disabled={!canSend || !draft.trim()} aria-label="Send message"><Send size={17} /></button>
        </form>
        <p>Changes require your confirmation.</p>
      </div>
    </section>}
    {!open && <button ref={launcher} type="button" className="tali-launcher" onClick={() => setOpen(true)} aria-label="Open Tali assistant" aria-expanded={false} aria-controls="tali-panel">
      <Sparkles size={19} aria-hidden="true" /><span>Ask Tali</span>
    </button>}
  </div>
}
