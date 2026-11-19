import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, BriefcaseBusiness, ShieldCheck, UserRound, Wallet } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardBody, ErrorState, Skeleton } from '@/components/ui/card'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'

interface Account { key: string; label: string; name: string; email: string }
const descriptions: Record<string, string> = { admin: 'Manage people, approve requests, finalize payroll and configure your organization.', employee: 'Check in, request leave, submit an expense, view payslips and track your goals.', manager: 'Review your team’s requests, assign tasks and complete performance reviews.', finance: 'Prepare payroll, review expense claims and follow reimbursements.' }
const icons = { admin: ShieldCheck, employee: UserRound, manager: BriefcaseBusiness, finance: Wallet }

export function DemoPage() {
  const q = useGet<Account[]>('/demo/accounts')
  const qc = useQueryClient()
  const nav = useNavigate()
  const enter = useSend<{ account: string }>('POST', '/demo/login', {
    onSuccess: (_r, b) => { qc.clear(); nav(b.account === 'employee' ? '/me' : '/') },
  })
  return <div className="min-h-screen bg-bg px-5 py-10 sm:py-16"><div className="mx-auto max-w-4xl">
    <Link to="/welcome" className="mb-10 inline-flex items-center gap-2 text-lg font-bold"><img src="/logo-mark.png" alt="" className="h-9 w-9" />Talvynza</Link>
    <p className="text-xs font-bold uppercase tracking-widest text-primary">Your local test workspace</p><h1 className="mt-3 text-4xl font-bold tracking-tight">See both sides of a working day.</h1><p className="mt-4 max-w-2xl text-base leading-7 text-muted">Choose a role to explore Talvynza. These are fictional accounts in a shared demo organization. Changes are saved, so you can submit a request as an employee and review it as an admin.</p>
    {q.isLoading ? <Skeleton className="mt-8 h-64 w-full" /> : q.isError ? <Card className="mt-8"><ErrorState message="The local demo is not running. Start it with scripts/start-demo.ps1, or sign in with your own account." onRetry={() => q.refetch()} /><CardBody className="pt-0 text-center"><Button asChild><Link to="/login">Go to sign in</Link></Button></CardBody></Card> : <div className="mt-9 grid gap-4 sm:grid-cols-2">{q.data?.map(a => { const Icon = icons[a.key as keyof typeof icons] ?? UserRound; return <Card key={a.key} className="transition-shadow hover:shadow-pop"><CardBody className="flex h-full flex-col"><span className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-primary-soft text-primary"><Icon className="h-5 w-5" /></span><h2 className="text-xl font-bold">{a.label}</h2><p className="mt-1 text-sm text-muted">{a.name}</p><p className="my-4 flex-1 text-sm leading-6 text-muted">{descriptions[a.key]}</p><Button variant={a.key === 'admin' ? 'primary' : 'outline'} disabled={enter.isPending} onClick={() => enter.mutate({ account: a.key })}>Enter as {a.label.toLowerCase()}<ArrowRight className="ml-auto h-4 w-4" /></Button></CardBody></Card> })}</div>}
    {enter.isError && <p className="mt-4 text-sm text-danger" role="alert">{errorMessage(enter.error)}</p>}
    <div className="mt-8 rounded-xl border border-border bg-surface px-5 py-4 text-sm text-muted"><strong className="text-fg">A good first test:</strong> enter as an employee, submit leave or an expense, then use “Switch demo role” in the sidebar to review it as a manager or administrator.</div>
    <p className="mt-6 text-xs text-subtle">Demo access is explicitly enabled only by the local launcher. Do not enter real personal or banking information.</p>
  </div></div>
}
