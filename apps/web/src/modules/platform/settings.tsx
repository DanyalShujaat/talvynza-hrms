import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Field, Input, Select } from '@/components/ui/form'
import { api, errorMessage } from '@/lib/api'
import { useMe, useOrg, useSessions } from '@/lib/queries'
import { formatDate } from '@/lib/utils'

// ------------------------------------------------------------------ Organization settings
const orgSchema = z.object({
  name: z.string().min(2), legal_name: z.string().optional(), timezone: z.string().min(3),
  expected_employee_count: z.coerce.number().int().min(1).optional(),
})

export function OrgSettingsPage() {
  const q = useOrg()
  const qc = useQueryClient()
  const { register, handleSubmit, reset, formState: { errors, isDirty } } = useForm({ resolver: zodResolver(orgSchema) })
  React.useEffect(() => {
    if (q.data) reset({ name: q.data.name, legal_name: q.data.legal_name ?? '', timezone: q.data.timezone, expected_employee_count: q.data.expected_employee_count ?? undefined })
  }, [q.data, reset])
  const m = useMutation({
    mutationFn: (b: z.output<typeof orgSchema>) => api('/organization', { method: 'PATCH', body: b }),
    onSuccess: () => { toast.success('Organization updated'); qc.invalidateQueries({ queryKey: ['org'] }); qc.invalidateQueries({ queryKey: ['me'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const zones = React.useMemo(() => (typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : ['UTC']), [])
  return (
    <>
      <PageHeader title="Organization" description="Business profile and regional defaults." />
      <Card className="max-w-2xl">
        {q.isLoading ? <CardBody><Skeleton className="h-40 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : (
          <CardBody>
            <form onSubmit={handleSubmit((v) => m.mutate(v))} className="space-y-4" noValidate>
              <Field id="name" label="Display name" error={errors.name?.message}>{(a) => <Input {...a} {...register('name')} />}</Field>
              <Field id="legal_name" label="Legal name">{(a) => <Input {...a} {...register('legal_name')} />}</Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="timezone" label="Time zone">{(a) => <Select {...a} {...register('timezone')}>{zones.map((z) => <option key={z}>{z}</option>)}</Select>}</Field>
                <Field id="emp" label="Expected employees">{(a) => <Input type="number" min={1} {...a} {...register('expected_employee_count')} />}</Field>
              </div>
              <div className="grid gap-4 text-sm sm:grid-cols-3">
                <div><p className="text-muted">Country</p><p className="font-medium">{q.data!.country}</p></div>
                <div><p className="text-muted">Currency</p><p className="font-medium">{q.data!.currency}</p></div>
                <div><p className="text-muted">Plan</p><p className="font-medium capitalize">{q.data!.plan_code} ({q.data!.status})</p></div>
              </div>
              <p className="text-xs text-muted">Country and currency are fixed after creation because they drive statutory and payroll configuration.</p>
              <Button type="submit" loading={m.isPending} disabled={!isDirty}>Save changes</Button>
            </form>
          </CardBody>)}
      </Card>
    </>
  )
}

// ------------------------------------------------------------------ Create organization
export function NewOrganizationPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: me } = useMe()
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(z.object({ name: z.string().min(2), country: z.string().length(2, 'Two-letter code'), currency: z.string().length(3, 'Three-letter code'), timezone: z.string().min(3) })),
    defaultValues: { country: 'PK', currency: 'PKR', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
  })
  const m = useMutation({
    mutationFn: async (b: Record<string, string>) => {
      const org = await api<{ id: string }>('/organizations', { method: 'POST', body: b })
      await api('/me/switch-organization', { method: 'POST', body: { tenant_id: org.id } })
    },
    onSuccess: async () => { qc.clear(); toast.success('Organization created'); nav('/') },
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <>
      <PageHeader title="Create organization" description={me?.active_organization ? 'Add another organization to your account.' : 'You are not a member of any active organization yet.'} />
      <Card className="max-w-xl"><CardBody>
        <form onSubmit={handleSubmit((v) => m.mutate(v))} className="space-y-4" noValidate>
          <Field id="name" label="Organization name" error={errors.name?.message}>{(a) => <Input {...a} {...register('name')} />}</Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field id="country" label="Country (ISO)" error={errors.country?.message}>{(a) => <Input maxLength={2} {...a} {...register('country')} />}</Field>
            <Field id="currency" label="Currency (ISO)" error={errors.currency?.message}>{(a) => <Input maxLength={3} {...a} {...register('currency')} />}</Field>
            <Field id="timezone" label="Time zone" error={errors.timezone?.message}>{(a) => <Input {...a} {...register('timezone')} />}</Field>
          </div>
          <Button type="submit" loading={m.isPending}>Create organization</Button>
        </form>
      </CardBody></Card>
    </>
  )
}

// ------------------------------------------------------------------ Security
function MfaCard() {
  const { data: me } = useMe()
  const qc = useQueryClient()
  const [setup, setSetup] = React.useState<{ secret: string; otpauth_uri: string } | null>(null)
  const [codes, setCodes] = React.useState<string[] | null>(null)
  const [code, setCode] = React.useState('')
  const [password, setPassword] = React.useState('')
  const refresh = () => qc.invalidateQueries({ queryKey: ['me'] })
  const begin = useMutation({ mutationFn: () => api<{ secret: string; otpauth_uri: string }>('/auth/mfa/setup', { method: 'POST' }), onSuccess: setSetup, onError: (e) => toast.error(errorMessage(e)) })
  const enable = useMutation({ mutationFn: () => api<{ recovery_codes: string[] }>('/auth/mfa/enable', { method: 'POST', body: { code } }), onSuccess: (r) => { setCodes(r.recovery_codes); setSetup(null); setCode(''); refresh() }, onError: (e) => toast.error(errorMessage(e)) })
  const disable = useMutation({ mutationFn: () => api('/auth/mfa/disable', { method: 'POST', body: { code, password } }), onSuccess: () => { toast.success('MFA disabled'); setCode(''); setPassword(''); refresh() }, onError: (e) => toast.error(errorMessage(e)) })
  return (
    <Card>
      <CardHeader><CardTitle>Multi-factor authentication</CardTitle><Badge tone={me?.identity.mfa_enabled ? 'success' : 'warning'}>{me?.identity.mfa_enabled ? 'Enabled' : 'Off'}</Badge></CardHeader>
      <CardBody className="space-y-4">
        {codes && (
          <div role="status" className="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
            <p className="font-medium">Save your recovery codes now. They are shown only once.</p>
            <ul className="mt-2 grid grid-cols-2 gap-1 font-mono text-xs">{codes.map((c) => <li key={c}>{c}</li>)}</ul>
          </div>)}
        {!me?.identity.mfa_enabled && !setup && <Button onClick={() => begin.mutate()} loading={begin.isPending}>Set up authenticator app</Button>}
        {setup && (
          <div className="space-y-3 text-sm">
            <p>Add this key to your authenticator app (Google Authenticator, 1Password, Authy…), then enter the 6-digit code.</p>
            <code className="block break-all rounded-lg bg-surface-2 p-3 text-xs">{setup.secret}</code>
            <a className="text-primary hover:underline" href={setup.otpauth_uri}>Open in authenticator app</a>
            <div className="flex gap-2"><Input inputMode="numeric" placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Authenticator code" className="max-w-40" /><Button onClick={() => enable.mutate()} loading={enable.isPending} disabled={code.length < 6}>Verify & enable</Button></div>
          </div>)}
        {me?.identity.mfa_enabled && (
          <div className="space-y-2 text-sm"><p className="text-muted">To turn MFA off, confirm your password and a current code.</p>
            <div className="flex flex-wrap gap-2"><Input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Password" className="max-w-52" /><Input placeholder="Code" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Code" className="max-w-36" /><Button variant="danger" onClick={() => disable.mutate()} loading={disable.isPending} disabled={!password || !code}>Disable MFA</Button></div></div>)}
      </CardBody>
    </Card>
  )
}

function SessionsCard() {
  const q = useSessions()
  const qc = useQueryClient()
  const revoke = useMutation({ mutationFn: (id: string) => api(`/auth/sessions/${id}`, { method: 'DELETE' }), onSuccess: () => { toast.success('Session signed out'); qc.invalidateQueries({ queryKey: ['sessions'] }) }, onError: (e) => toast.error(errorMessage(e)) })
  return (
    <Card>
      <CardHeader><CardTitle>Active sessions</CardTitle></CardHeader>
      {q.isLoading ? <CardBody><Skeleton className="h-16 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : (
        <ul className="divide-y divide-border">{q.data!.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
            <div className="min-w-0"><p className="truncate">{s.user_agent ?? 'Unknown device'} {s.current && <Badge tone="success" className="ml-1">this device</Badge>}</p><p className="text-xs text-muted">{s.ip ?? '-'} · last active {formatDate(s.last_seen_at)}</p></div>
            {!s.current && <Button variant="outline" size="sm" onClick={() => revoke.mutate(s.id)}>Sign out</Button>}
          </li>))}</ul>)}
    </Card>
  )
}

function PasswordCard() {
  const [serverError, setServerError] = React.useState<string | null>(null)
  const { register, handleSubmit, reset, formState: { errors } } = useForm<{ current_password: string; new_password: string }>({ resolver: zodResolver(z.object({ current_password: z.string().min(1, 'Required'), new_password: z.string().min(12, 'Use at least 12 characters') })) })
  const m = useMutation({ mutationFn: (b: { current_password: string; new_password: string }) => api('/auth/change-password', { method: 'POST', body: b }), onSuccess: () => { toast.success('Password changed; other sessions were signed out'); reset(); setServerError(null) }, onError: (e) => setServerError(errorMessage(e)) })
  return (
    <Card>
      <CardHeader><CardTitle>Change password</CardTitle></CardHeader>
      <CardBody>
        <form onSubmit={handleSubmit((v) => m.mutate(v))} className="max-w-sm space-y-4" noValidate>
          {serverError && <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{serverError}</p>}
          <Field id="cur" label="Current password" error={errors.current_password?.message}>{(a) => <Input type="password" autoComplete="current-password" {...a} {...register('current_password')} />}</Field>
          <Field id="new" label="New password" error={errors.new_password?.message}>{(a) => <Input type="password" autoComplete="new-password" {...a} {...register('new_password')} />}</Field>
          <Button type="submit" loading={m.isPending}>Update password</Button>
        </form>
      </CardBody>
    </Card>
  )
}

export function SecurityPage() {
  return (
    <>
      <PageHeader title="Security" description="Protect your account and review where you are signed in." />
      <div className="grid max-w-3xl gap-4"><MfaCard /><SessionsCard /><PasswordCard /></div>
    </>
  )
}
