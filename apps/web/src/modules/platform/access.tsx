import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, UserPlus } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Field, Input, Select } from '@/components/ui/form'
import { api, errorMessage } from '@/lib/api'
import { useSend } from '@/lib/hooks'
import { ConfirmButton } from '@/components/ui/extras'
import { useAudit, useMe, useMembers, usePermissions, useRoles } from '@/lib/queries'
import { formatDate } from '@/lib/utils'

function InviteDialog() {
  const [open, setOpen] = React.useState(false)
  const roles = useRoles()
  const qc = useQueryClient()
  const { register, handleSubmit, reset, formState: { errors } } = useForm<{ email: string; role_key: string }>({
    resolver: zodResolver(z.object({ email: z.string().email('Enter a valid email'), role_key: z.string().min(1) })), defaultValues: { role_key: 'employee' },
  })
  const m = useMutation({
    mutationFn: (b: { email: string; role_key: string }) => api('/invitations', { method: 'POST', body: b }),
    onSuccess: () => { toast.success('Invitation sent'); setOpen(false); reset(); qc.invalidateQueries({ queryKey: ['audit'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}><UserPlus className="h-4 w-4" />Invite user</Button>
      <DialogContent title="Invite a teammate" description="They receive an email link valid for 7 days. You can only assign roles whose permissions you already hold.">
        <form onSubmit={handleSubmit((v) => m.mutate(v))} className="space-y-4" noValidate>
          <Field id="inv-email" label="Email" error={errors.email?.message}>{(a) => <Input type="email" {...a} {...register('email')} />}</Field>
          <Field id="inv-role" label="Role">{(a) => <Select {...a} {...register('role_key')}>{roles.data?.map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}</Select>}</Field>
          <div className="flex justify-end gap-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={m.isPending}>Send invitation</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function EditRolesDialog({ membershipId, current, name }: { membershipId: string; current: string[]; name: string }) {
  const [open, setOpen] = React.useState(false)
  const [sel, setSel] = React.useState<Set<string>>(new Set(current))
  const roles = useRoles()
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () => api(`/members/${membershipId}/roles`, { method: 'PUT', body: { role_keys: [...sel] } }),
    onSuccess: () => {
      toast.success('Roles updated')
      setOpen(false)
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['/members'] })
      qc.invalidateQueries({ queryKey: ['audit'] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) setSel(new Set(current)) }}>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>Edit roles</Button>
      <DialogContent title={`Roles for ${name}`} description="Permissions are the union of all assigned roles.">
        <div className="max-h-72 space-y-1 overflow-auto">
          {roles.data?.map((r) => (
            <label key={r.key} className="flex cursor-pointer items-start gap-3 rounded-lg p-2 hover:bg-surface-2">
              <input type="checkbox" className="mt-1" checked={sel.has(r.key)} onChange={(e) => setSel((s) => { const n = new Set(s); e.target.checked ? n.add(r.key) : n.delete(r.key); return n })} />
              <span><span className="text-sm font-medium">{r.name}</span><span className="block text-xs text-muted">{r.description ?? `${r.permissions.length} permissions`}</span></span>
            </label>
          ))}
        </div>
        <div className="mt-4 flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button onClick={() => m.mutate()} loading={m.isPending} disabled={sel.size === 0}>Save roles</Button></div>
      </DialogContent>
    </Dialog>
  )
}

export function MembersPage() {
  const [page, setPage] = React.useState(1)
  const { data: me } = useMe()
  const q = useMembers(page)
  const canManage = me?.permissions.includes('members.manage')
  const remove = useSend<string>('DELETE', (id) => `/members/${id}`, { invalidate: ['members', '/employees'], success: 'Access removed' })
  return (
    <>
      <PageHeader title="Users" description="People who can sign in to this organization, and their roles." actions={canManage ? <InviteDialog /> : undefined} />
      <Card>
        {q.isLoading ? <div className="space-y-3 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} />
          : q.data!.items.length === 0 ? <EmptyState title="No members yet" />
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-xs uppercase text-muted"><tr><th className="px-5 py-3 font-medium">Name</th><th className="px-5 py-3 font-medium">Roles</th><th className="px-5 py-3 font-medium">Status</th><th className="px-5 py-3" /></tr></thead>
                <tbody className="divide-y divide-border">
                  {q.data!.items.map((m) => (
                    <tr key={m.membership_id}>
                      <td className="px-5 py-3"><p className="font-medium">{m.full_name}</p><p className="text-xs text-muted">{m.email}</p></td>
                      <td className="px-5 py-3"><div className="flex flex-wrap gap-1">{m.roles.map((r) => <Badge key={r} tone="primary">{r.replace('_', ' ')}</Badge>)}</div></td>
                      <td className="px-5 py-3"><Badge tone={m.status === 'active' ? 'success' : 'warning'} className="capitalize">{m.status}</Badge></td>
                      <td className="space-x-2 px-5 py-3 text-right">{canManage && <EditRolesDialog membershipId={m.membership_id} current={m.roles} name={m.full_name} />}{canManage && m.identity_id !== me?.identity.id && <ConfirmButton label="Remove" title={`Remove ${m.full_name}?`} message="They lose access to this organization immediately. Their employee record and history are kept, and they can be invited again." confirmLabel="Remove access" onConfirm={() => remove.mutate(m.membership_id)} />}</td>
                    </tr>))}
                </tbody>
              </table>
              <div className="flex items-center justify-between border-t border-border px-5 py-3 text-sm text-muted">
                <span>{q.data!.total} total</span>
                <div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button><Button variant="outline" size="sm" disabled={page * q.data!.page_size >= q.data!.total} onClick={() => setPage((p) => p + 1)}>Next</Button></div>
              </div>
            </div>)}
      </Card>
    </>
  )
}

// ------------------------------------------------------------------ Roles
function CreateRoleDialog() {
  const [open, setOpen] = React.useState(false)
  const [sel, setSel] = React.useState<Set<string>>(new Set())
  const [name, setName] = React.useState('')
  const { data: me } = useMe()
  const perms = usePermissions(open)
  const qc = useQueryClient()
  const own = new Set(me?.permissions ?? [])
  const m = useMutation({
    mutationFn: () => api('/roles', { method: 'POST', body: { key: name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_'), name: name.trim(), permissions: [...sel] } }),
    onSuccess: () => { toast.success('Role created'); setOpen(false); setName(''); setSel(new Set()); qc.invalidateQueries({ queryKey: ['roles'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const byModule = (perms.data ?? []).reduce<Record<string, NonNullable<typeof perms.data>>>((acc, p) => { (acc[p.module] ??= []).push(p); return acc }, {})
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Custom role</Button>
      <DialogContent className="max-w-2xl" title="Create custom role" description="You can only grant permissions you hold yourself (greyed-out items are unavailable).">
        <Field id="role-name" label="Role name">{(a) => <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Operations Lead" {...a} />}</Field>
        <div className="mt-4 max-h-72 space-y-4 overflow-auto pr-1">
          {Object.entries(byModule).map(([mod, list]) => (
            <fieldset key={mod}><legend className="mb-1 text-xs font-semibold uppercase text-muted">{mod}</legend>
              {list.map((p) => (
                <label key={p.code} className={`flex items-start gap-2 py-1 text-sm ${own.has(p.code) ? 'cursor-pointer' : 'cursor-not-allowed opacity-40'}`}>
                  <input type="checkbox" className="mt-1" disabled={!own.has(p.code)} checked={sel.has(p.code)} onChange={(e) => setSel((s) => { const n = new Set(s); e.target.checked ? n.add(p.code) : n.delete(p.code); return n })} />
                  <span>{p.description}{p.is_sensitive && <Badge tone="warning" className="ml-2">sensitive</Badge>}<span className="block font-mono text-[11px] text-muted">{p.code}</span></span>
                </label>))}
            </fieldset>))}
        </div>
        <div className="mt-4 flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button onClick={() => m.mutate()} loading={m.isPending} disabled={name.trim().length < 3}>Create role</Button></div>
      </DialogContent>
    </Dialog>
  )
}

export function RolesPage() {
  const { data: me } = useMe()
  const q = useRoles()
  return (
    <>
      <PageHeader title="Roles & access" description="Default roles are locked; create custom roles for anything else." actions={me?.permissions.includes('roles.manage') ? <CreateRoleDialog /> : undefined} />
      {q.isLoading ? <Skeleton className="h-64 w-full" /> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {q.data!.map((r) => (
            <Card key={r.id} className="p-5">
              <div className="flex items-start justify-between gap-2"><div><h3 className="font-semibold">{r.name}</h3><p className="text-sm text-muted">{r.description}</p></div><Badge tone={r.is_system ? 'neutral' : 'primary'}>{r.is_system ? 'default' : 'custom'}</Badge></div>
              <p className="mt-3 text-xs text-muted">{r.permissions.length} permissions</p>
              <details className="mt-1"><summary className="cursor-pointer text-xs text-primary">Show permissions</summary><p className="mt-2 flex flex-wrap gap-1">{r.permissions.map((p) => <code key={p} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">{p}</code>)}</p></details>
            </Card>))}
        </div>)}
    </>
  )
}

// ------------------------------------------------------------------ Audit
export function AuditPage() {
  const [page, setPage] = React.useState(1)
  const q = useAudit(page)
  return (
    <>
      <PageHeader title="Audit log" description="Append-only record of security-relevant changes in this organization." />
      <Card>
        {q.isLoading ? <div className="space-y-3 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} />
          : q.data!.items.length === 0 ? <EmptyState title="No audit events" />
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-xs uppercase text-muted"><tr><th className="px-5 py-3 font-medium">When</th><th className="px-5 py-3 font-medium">Action</th><th className="px-5 py-3 font-medium">Entity</th><th className="px-5 py-3 font-medium">Details</th></tr></thead>
                <tbody className="divide-y divide-border">{q.data!.items.map((a) => (
                  <tr key={a.id}><td className="whitespace-nowrap px-5 py-3 text-muted">{formatDate(a.created_at)}</td><td className="px-5 py-3 font-mono text-xs">{a.action}</td><td className="px-5 py-3">{a.entity_type}</td><td className="max-w-xs truncate px-5 py-3 font-mono text-xs text-muted">{JSON.stringify(a.details)}</td></tr>))}</tbody>
              </table>
              <div className="flex items-center justify-between border-t border-border px-5 py-3 text-sm text-muted"><span>{q.data!.total} events</span>
                <div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Newer</Button><Button variant="outline" size="sm" disabled={page * q.data!.page_size >= q.data!.total} onClick={() => setPage((p) => p + 1)}>Older</Button></div></div>
            </div>)}
      </Card>
    </>
  )
}
