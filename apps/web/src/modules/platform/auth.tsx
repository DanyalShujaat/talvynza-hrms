import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, MailCheck, Users, CalendarDays, Wallet, Sparkles } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Card, CardBody, ErrorState } from '@/components/ui/card'
import { Field, Input, Select } from '@/components/ui/form'
import { ApiError, api, errorMessage } from '@/lib/api'
import './auth.css'

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="auth-page grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="auth-stage relative hidden flex-col justify-between overflow-hidden p-10 text-white lg:flex xl:p-14">
        <Link to="/welcome" className="relative z-10 flex w-fit items-center gap-3" aria-label="Talvynza home"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white p-1.5"><img src="/logo-mark.png" alt="" className="h-full w-full" /></span><span className="font-display text-xl font-extrabold">Talvynza<span className="text-cyan-300">.</span></span></Link>
        <div className="relative z-10 my-12 max-w-xl"><p className="inline-flex items-center gap-2 rounded-full border border-cyan-200/20 bg-white/10 px-4 py-2 text-xs font-semibold text-cyan-100"><Sparkles className="h-4 w-4" /> Your connected workspace starts here</p><h2 className="mt-6 font-display text-4xl font-extrabold leading-[1.12] tracking-tight xl:text-5xl">Bring your people, time and pay <span className="text-cyan-200">together.</span></h2><p className="mt-5 max-w-md text-base leading-7 text-slate-300">A clearer home for the entire employee journey, from the first application to every working day.</p>
          <div className="auth-preview mt-10"><div className="flex items-center justify-between border-b border-white/10 px-5 py-4"><span className="text-xs font-bold uppercase tracking-widest text-cyan-200">Your Talvynza workspace</span><span className="h-2 w-2 rounded-full bg-emerald-400" /></div><div className="grid grid-cols-3 gap-3 p-5">{[[Users,'People','Connected'],[CalendarDays,'Time','In sync'],[Wallet,'Pay','In context']].map(([Icon,label,detail])=><div key={label as string} className="rounded-xl border border-white/10 bg-white/[.06] p-4"><Icon className="mb-5 h-5 w-5 text-cyan-200" /><strong className="block text-sm">{label as string}</strong><small className="text-slate-400">{detail as string}</small></div>)}</div></div>
        </div><p className="relative z-10 flex items-center gap-2 text-xs text-slate-300"><CheckCircle2 className="h-4 w-4 text-teal-300" /> One secure workspace for your team</p>
      </div>
      <div className="auth-form-side flex items-center justify-center px-5 py-10 sm:px-10 lg:py-14">
        <div className="auth-card w-full max-w-[510px]"><div className="flex items-center justify-between gap-4"><Link to="/welcome" className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-[#0f4bb5]">← Back to Talvynza</Link><img src="/logo-mark.png" alt="Talvynza HRMS" className="h-9 w-9 lg:hidden" /></div><div className="mt-8"><p className="text-xs font-bold uppercase tracking-[.18em] text-[#078e91]">Talvynza HRMS</p><h1 className="mt-2 font-display text-[30px] font-extrabold tracking-tight text-[#10233f]">{title}</h1>{subtitle && <p className="mt-2 text-sm leading-6 text-slate-500">{subtitle}</p>}</div><div className="mt-7">{children}</div><div className="mt-6 flex items-center gap-2 border-t border-slate-200 pt-5 text-xs text-slate-400"><CheckCircle2 className="h-4 w-4 text-teal-600" /> Your workspace is private to your organization <ArrowRight className="ml-auto h-3 w-3 text-teal-600" /></div></div>
      </div>
    </div>
  )
}

const FormError = ({ message }: { message?: string | null }) =>
  message ? <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{message}</p> : null

// ------------------------------------------------------------------ Login
const loginSchema = z.object({ email: z.string().email('Enter a valid email'), password: z.string().min(1, 'Password is required'), mfa_code: z.string().optional() })

export function LoginPage() {
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const employeeView = params.get('view') === 'employee'
  const qc = useQueryClient()
  const [needsMfa, setNeedsMfa] = React.useState(false)
  const [serverError, setServerError] = React.useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema) })
  const login = useMutation({
    mutationFn: (b: z.infer<typeof loginSchema>) => api('/auth/login', { method: 'POST', body: { ...b, mfa_code: b.mfa_code || undefined } }),
    onSuccess: async () => {
      qc.clear()
      const from = location.state?.from
      nav(typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') ? from : employeeView ? '/me' : '/')
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'mfa_required') { setNeedsMfa(true); setServerError(null) } else setServerError(errorMessage(e))
    },
  })
  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your Talvynza workspace.">
      <div className="mb-6 flex rounded-lg bg-surface-2 p-1" role="group" aria-label="Workspace view">
        {[['admin', 'Admin & manager'], ['employee', 'Employee']].map(([key, label]) => <button key={key} type="button" aria-pressed={employeeView === (key === 'employee')} onClick={() => setParams({ view: key })} className={`flex-1 cursor-pointer rounded-md px-3 py-2 text-sm font-medium ${employeeView === (key === 'employee') ? 'bg-surface text-primary shadow-sm' : 'text-muted'}`}>{label}</button>)}
      </div>
      <form onSubmit={handleSubmit((v) => login.mutate(v))} className="space-y-4" noValidate>
        <FormError message={serverError} />
        <Field id="email" label="Work email" error={errors.email?.message}>{(a) => <Input type="email" autoComplete="username" {...a} {...register('email')} />}</Field>
        <Field id="password" label="Password" error={errors.password?.message}>{(a) => <Input type="password" autoComplete="current-password" {...a} {...register('password')} />}</Field>
        {needsMfa && (
          <Field id="mfa" label="Authenticator or recovery code" hint="Enter the 6-digit code from your authenticator app.">
            {(a) => <Input inputMode="numeric" autoComplete="one-time-code" autoFocus {...a} {...register('mfa_code')} />}
          </Field>
        )}
        <Button type="submit" size="lg" className="w-full" loading={login.isPending}>Sign in</Button>
        <div className="flex justify-between text-sm"><Link to="/forgot-password" className="text-primary hover:underline">Forgot password?</Link><Link to="/register" className="text-primary hover:underline">Create an account</Link></div>
      </form>
    </AuthLayout>
  )
}

// ------------------------------------------------------------------ Register
const COUNTRIES = [
  { code: 'PK', name: 'Pakistan', currency: 'PKR', tz: 'Asia/Karachi' },
  { code: 'GB', name: 'United Kingdom', currency: 'GBP', tz: 'Europe/London' },
  { code: 'AE', name: 'United Arab Emirates', currency: 'AED', tz: 'Asia/Dubai' },
  { code: 'SA', name: 'Saudi Arabia', currency: 'SAR', tz: 'Asia/Riyadh' },
  { code: 'US', name: 'United States', currency: 'USD', tz: 'America/New_York' },
  { code: 'DE', name: 'Germany', currency: 'EUR', tz: 'Europe/Berlin' },
  { code: 'IN', name: 'India', currency: 'INR', tz: 'Asia/Kolkata' },
]
const regSchema = z.object({
  full_name: z.string().min(2, 'Enter your full name'),
  email: z.string().email('Enter a valid email'),
  password: z.string().min(12, 'Use at least 12 characters'),
  organization_name: z.string().min(2, 'Enter your organization name'),
  country: z.string().length(2),
  expected_employee_count: z.coerce.number().int().min(1, 'Enter at least 1').max(1_000_000),
})

export function RegisterPage() {
  const [done, setDone] = React.useState<{ email: string; verificationRequired: boolean } | null>(null)
  const [serverError, setServerError] = React.useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm({ resolver: zodResolver(regSchema), defaultValues: { country: 'PK', expected_employee_count: 25 } })
  const reg = useMutation({
    mutationFn: (v: z.output<typeof regSchema>) => {
      const c = COUNTRIES.find((x) => x.code === v.country)!
      return api<{ verification_required: boolean }>('/auth/register', { method: 'POST', body: { ...v, currency: c.currency, timezone: c.tz } })
    },
    onSuccess: (data, v) => setDone({ email: v.email, verificationRequired: data.verification_required }),
    onError: (e) => setServerError(errorMessage(e)),
  })
  if (done) {
    return (
      <AuthLayout title={done.verificationRequired ? 'Check your inbox' : 'Your registration is ready'}>
        <Card><CardBody className="flex flex-col items-center gap-3 text-center">
          <MailCheck className="h-10 w-10 text-primary" />
          <p className="text-sm">{done.verificationRequired ? <>If the details are valid, we sent a verification link to <strong>{done.email}</strong>. Verify your email, then sign in.</> : <>If this is a new account, you can now sign in with <strong>{done.email}</strong> and finish setting up your organization.</>}</p>
          <Button asChild variant="outline"><Link to="/login">Go to sign in</Link></Button>
        </CardBody></Card>
      </AuthLayout>
    )
  }
  return (
    <AuthLayout title="Create your organization" subtitle="Start a free trial. No payment needed to configure your workspace.">
      <form onSubmit={handleSubmit((v) => reg.mutate(v))} className="space-y-4" noValidate>
        <FormError message={serverError} />
        <Field id="full_name" label="Your full name" error={errors.full_name?.message}>{(a) => <Input autoComplete="name" {...a} {...register('full_name')} />}</Field>
        <Field id="email" label="Work email" error={errors.email?.message}>{(a) => <Input type="email" autoComplete="email" {...a} {...register('email')} />}</Field>
        <Field id="password" label="Password" hint="12+ characters, mixing at least three of: lowercase, uppercase, digits, symbols." error={errors.password?.message}>{(a) => <Input type="password" autoComplete="new-password" {...a} {...register('password')} />}</Field>
        <Field id="organization_name" label="Organization name" error={errors.organization_name?.message}>{(a) => <Input autoComplete="organization" {...a} {...register('organization_name')} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="country" label="Country" hint="Sets default currency & time zone (editable later).">{(a) => <Select {...a} {...register('country')}>{COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select>}</Field>
          <Field id="expected_employee_count" label="Employees (approx.)" error={errors.expected_employee_count?.message}>{(a) => <Input type="number" min={1} {...a} {...register('expected_employee_count')} />}</Field>
        </div>
        <Button type="submit" size="lg" className="w-full" loading={reg.isPending}>Create account</Button>
        <p className="text-center text-sm text-muted">Already have an account? <Link to="/login" className="text-primary hover:underline">Sign in</Link></p>
      </form>
    </AuthLayout>
  )
}

// ------------------------------------------------------------------ Verify email
export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const q = useQuery({ queryKey: ['verify', token], enabled: !!token, retry: false, staleTime: Infinity, queryFn: () => api('/auth/verify-email', { method: 'POST', body: { token } }).then(() => true) })
  return (
    <AuthLayout title="Email verification">
      {!token ? <ErrorState message="This verification link is incomplete." />
        : q.isLoading ? <p className="text-sm text-muted">Verifying…</p>
        : q.isError ? <ErrorState message={errorMessage(q.error)} />
        : (<Card><CardBody className="flex flex-col items-center gap-3 text-center"><CheckCircle2 className="h-10 w-10 text-success" /><p>Your email is verified.</p><Button asChild><Link to="/login">Continue to sign in</Link></Button></CardBody></Card>)}
    </AuthLayout>
  )
}

// ------------------------------------------------------------------ Forgot / reset password
export function ForgotPasswordPage() {
  const [sent, setSent] = React.useState(false)
  const { register, handleSubmit, formState: { errors } } = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email: z.string().email('Enter a valid email') })) })
  const m = useMutation({ mutationFn: (b: { email: string }) => api('/auth/forgot-password', { method: 'POST', body: b }), onSuccess: () => setSent(true), onError: (e) => toast.error(errorMessage(e)) })
  return (
    <AuthLayout title="Reset your password" subtitle="We'll email you a link if an account exists for that address.">
      {sent ? <p className="rounded-lg bg-success/10 p-3 text-sm">If an account exists, a reset link is on its way. It expires in 1 hour.</p> : (
        <form onSubmit={handleSubmit((v) => m.mutate(v))} className="space-y-4" noValidate>
          <Field id="email" label="Email" error={errors.email?.message}>{(a) => <Input type="email" {...a} {...register('email')} />}</Field>
          <Button type="submit" className="w-full" loading={m.isPending}>Send reset link</Button>
        </form>
      )}
      <p className="mt-4 text-center text-sm"><Link to="/login" className="text-primary hover:underline">Back to sign in</Link></p>
    </AuthLayout>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const [serverError, setServerError] = React.useState<string | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<{ new_password: string }>({ resolver: zodResolver(z.object({ new_password: z.string().min(12, 'Use at least 12 characters') })) })
  const m = useMutation({
    mutationFn: (b: { new_password: string }) => api('/auth/reset-password', { method: 'POST', body: { token: params.get('token'), ...b } }),
    onSuccess: () => { toast.success('Password updated. Please sign in.'); nav('/login') },
    onError: (e) => setServerError(errorMessage(e)),
  })
  return (
    <AuthLayout title="Choose a new password">
      <form onSubmit={handleSubmit((v) => m.mutate(v))} className="space-y-4" noValidate>
        <FormError message={serverError} />
        <Field id="new_password" label="New password" error={errors.new_password?.message}>{(a) => <Input type="password" autoComplete="new-password" {...a} {...register('new_password')} />}</Field>
        <Button type="submit" className="w-full" loading={m.isPending}>Update password</Button>
      </form>
    </AuthLayout>
  )
}

// ------------------------------------------------------------------ Join from an invitation
interface InviteInfo { email: string; organization: string | null; has_account: boolean }

/** The page an invitation email links to. New people set a name and password and are signed straight in.
 *  People who already have an account sign in and the invitation is accepted for them. */
export function JoinPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const nav = useNavigate()
  const qc = useQueryClient()
  const info = useQuery({ queryKey: ['invitation', token], enabled: !!token, retry: false, queryFn: () => api<InviteInfo>('/auth/invitation', { params: { token } }) })
  const [name, setName] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [serverError, setServerError] = React.useState<string | null>(null)
  const done = async () => { qc.clear(); nav('/me') }

  const join = useMutation({
    mutationFn: () => api('/auth/join', { method: 'POST', body: { token, full_name: name, password } }),
    onSuccess: done, onError: (e) => setServerError(errorMessage(e)),
  })
  const signInAndAccept = useMutation({
    mutationFn: async () => {
      await api('/auth/login', { method: 'POST', body: { email: info.data!.email, password } })
      const r = await api<{ tenant_id: string }>('/invitations/accept', { method: 'POST', body: { token } })
      await api('/me/switch-organization', { method: 'POST', body: { tenant_id: r.tenant_id } })
    },
    onSuccess: done, onError: (e) => setServerError(errorMessage(e)),
  })

  if (!token || info.isError) return <AuthLayout title="Invitation"><ErrorState message="This invitation link is invalid or has expired. Ask your HR team to send a new one." /></AuthLayout>
  if (info.isLoading || !info.data) return <AuthLayout title="Invitation"><p className="text-sm text-muted">Checking your invitation...</p></AuthLayout>
  const d = info.data
  return d.has_account ? (
    <AuthLayout title={`Join ${d.organization}`} subtitle="You already have a Talvynza account. Sign in to accept the invitation.">
      <form onSubmit={(e) => { e.preventDefault(); signInAndAccept.mutate() }} className="space-y-4" noValidate>
        <FormError message={serverError} />
        <Field id="j-email" label="Email">{(a) => <Input value={d.email} disabled readOnly {...a} />}</Field>
        <Field id="j-pass" label="Password">{(a) => <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} {...a} />}</Field>
        <Button type="submit" size="lg" className="w-full" loading={signInAndAccept.isPending} disabled={!password}>Sign in and join</Button>
      </form>
    </AuthLayout>
  ) : (
    <AuthLayout title={`Welcome to ${d.organization}`} subtitle="Set your name and a password to open your employee space.">
      <form onSubmit={(e) => { e.preventDefault(); join.mutate() }} className="space-y-4" noValidate>
        <FormError message={serverError} />
        <Field id="j-email" label="Email">{(a) => <Input value={d.email} disabled readOnly {...a} />}</Field>
        <Field id="j-name" label="Your full name">{(a) => <Input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} {...a} />}</Field>
        <Field id="j-pass" label="Choose a password" hint="At least 12 characters, mixing three of: lowercase, uppercase, digits, symbols.">{(a) => <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} {...a} />}</Field>
        <Button type="submit" size="lg" className="w-full" loading={join.isPending} disabled={name.trim().length < 2 || password.length < 12}>Create my account</Button>
      </form>
    </AuthLayout>
  )
}
