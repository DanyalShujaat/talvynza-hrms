import * as React from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import type { ModuleGuide } from './guides'

interface Box { top: number; left: number; right: number; bottom: number }

export function ModuleWalkthrough({ guide, step, onStep, onClose }: { guide: ModuleGuide; step: number; onStep: (step: number) => void; onClose: () => void }) {
  const [box, setBox] = React.useState<Box | null>(null)
  const nextRef = React.useRef<HTMLButtonElement>(null)
  const current = guide.steps[step]

  React.useEffect(() => {
    const candidates = [current.target, step === 0 ? '[data-tour="page-header"]' : undefined,
      step === 1 ? '[data-tour="page-actions"]' : undefined, '[role="tablist"]', 'main table', 'main h1'].filter(Boolean) as string[]
    const update = () => {
      const element = candidates.map(selector => document.querySelector<HTMLElement>(selector)).find(el => el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
      if (!element) { setBox(null); return }
      const rect = element.getBoundingClientRect()
      if (rect.bottom < 70 || rect.top > innerHeight - 70) { element.scrollIntoView({ block: 'center', behavior: 'auto' }); return }
      setBox({ top: Math.max(8, rect.top - 7), left: Math.max(8, rect.left - 7), right: Math.min(innerWidth - 8, rect.right + 7), bottom: Math.min(innerHeight - 8, rect.bottom + 7) })
    }
    const frame = requestAnimationFrame(update)
    const observer = new MutationObserver(update)
    const main = document.getElementById('main')
    if (main) observer.observe(main, { childList: true, subtree: true })
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => { cancelAnimationFrame(frame); observer.disconnect(); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [current.target, step, guide.title])
  React.useEffect(() => { nextRef.current?.focus() }, [step])
  React.useEffect(() => { const key = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key) }, [onClose])

  const cardWidth = Math.min(380, innerWidth - 32)
  const cardLeft = box ? Math.max(16, Math.min(box.left, innerWidth - cardWidth - 16)) : Math.max(16, (innerWidth - cardWidth) / 2)
  const below = !box || box.bottom + 250 < innerHeight
  const cardTop = box ? below ? Math.min(box.bottom + 16, innerHeight - 245) : Math.max(16, box.top - 230) : Math.max(16, (innerHeight - 240) / 2)
  return <div className="pointer-events-none fixed inset-0 z-[70]" role="dialog" aria-label={`${guide.title} walkthrough`}>
    {box ? <>
      <div className="absolute left-0 top-0 w-full bg-slate-950/60" style={{ height: box.top }} />
      <div className="absolute left-0 bg-slate-950/60" style={{ top: box.top, width: box.left, height: box.bottom - box.top }} />
      <div className="absolute right-0 bg-slate-950/60" style={{ top: box.top, left: box.right, height: box.bottom - box.top }} />
      <div className="absolute bottom-0 left-0 w-full bg-slate-950/60" style={{ top: box.bottom }} />
      <div className="pointer-events-none absolute rounded-lg ring-2 ring-primary ring-offset-2 ring-offset-transparent" style={{ top: box.top, left: box.left, width: box.right - box.left, height: box.bottom - box.top }} />
    </> : <div className="absolute inset-0 bg-slate-950/60" />}
    <div className="pointer-events-auto absolute rounded-2xl border border-border bg-surface p-5 text-fg shadow-2xl" style={{ top: cardTop, left: cardLeft, width: cardWidth }}>
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-primary">{guide.title} · {step + 1} of {guide.steps.length}</p><h2 className="mt-2 font-display text-lg font-bold">{current.title}</h2></div><button type="button" onClick={onClose} className="text-xs font-medium text-muted hover:text-fg" aria-label="Skip walkthrough">Skip</button></div>
      <p className="mt-3 text-sm leading-6 text-muted">{current.body}</p>
      {current.to && <Link to={current.to} onClick={onClose} className="mt-3 inline-block text-sm font-semibold text-primary hover:underline">Open {current.title.toLowerCase()}</Link>}
      <div className="mt-5 flex items-center justify-between"><div className="flex gap-1" aria-hidden>{guide.steps.map((_, i) => <span key={i} className={`h-1.5 w-5 rounded-full ${i === step ? 'bg-primary' : 'bg-border-strong'}`} />)}</div><div className="flex gap-2"><Button size="sm" variant="outline" disabled={step === 0} onClick={() => onStep(step - 1)}>Back</Button><Button ref={nextRef} size="sm" onClick={() => step + 1 < guide.steps.length ? onStep(step + 1) : onClose()}>{step + 1 < guide.steps.length ? 'Next' : 'Finish'}</Button></div></div>
    </div>
  </div>
}
