import { Moon, Plus } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { ConfirmButton, Td, Th } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { today, useGet, useSend } from '@/lib/hooks'
import { formatDate } from '@/lib/utils'
import { Opts, useOrgLists } from '@/modules/people/employees'

interface Shift { id: string; name: string; start_time: string; end_time: string; overnight: boolean; break_minutes: number; grace_minutes: number | null }
interface RosterRow { employee_id: string; employee_code: string; full_name: string; department: string | null; shift: string | null; effective_from: string | null }

function ShiftDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [f, setF] = React.useState({ name: '', start_time: '09:00', end_time: '18:00', break_minutes: 60, grace_minutes: '' })
  const m = useSend<Record<string, unknown>>('POST', '/shifts', { invalidate: ['/shifts'], success: 'Shift created', onSuccess: () => onOpenChange(false) })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New shift" description="If the end time is earlier than the start time, the shift ends the next day.">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2"><Field id="sh-n" label="Name">{(a) => <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} {...a} />}</Field></div>
          <Field id="sh-s" label="Starts">{(a) => <Input type="time" value={f.start_time} onChange={(e) => setF({ ...f, start_time: e.target.value })} {...a} />}</Field>
          <Field id="sh-e" label="Ends">{(a) => <Input type="time" value={f.end_time} onChange={(e) => setF({ ...f, end_time: e.target.value })} {...a} />}</Field>
          <Field id="sh-b" label="Unpaid break (min)">{(a) => <Input type="number" min={0} value={f.break_minutes} onChange={(e) => setF({ ...f, break_minutes: Number(e.target.value) })} {...a} />}</Field>
          <Field id="sh-g" label="Grace override (min)" hint="Blank uses the company policy.">{(a) => <Input type="number" min={0} value={f.grace_minutes} onChange={(e) => setF({ ...f, grace_minutes: e.target.value })} {...a} />}</Field>
          <div className="flex justify-end gap-2 sm:col-span-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button loading={m.isPending} disabled={f.name.trim().length < 2} onClick={() => m.mutate({ ...f, grace_minutes: f.grace_minutes === '' ? null : Number(f.grace_minutes) })}>Create shift</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function AssignDialog({ shifts, roster }: { shifts: Shift[]; roster: RosterRow[] }) {
  const [open, setOpen] = React.useState(false)
  const { departments } = useOrgLists()
  const [shift, setShift] = React.useState('')
  const [from, setFrom] = React.useState(today())
  const [dept, setDept] = React.useState('')
  const [sel, setSel] = React.useState<Set<string>>(new Set())
  const m = useSend<Record<string, unknown>, { assigned: number; warnings: string[] }>('POST', '/shifts/assign', {
    invalidate: ['/shifts', '/attendance'], onSuccess: (r) => { toast.success(`${r.assigned} employees assigned`); r.warnings.forEach((w) => toast.warning(w)); setOpen(false); setSel(new Set()) },
  })
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)} disabled={!shifts.length}>Assign shift</Button>
      <DialogContent className="max-w-xl" title="Assign a shift" description="The employee's previous assignment ends the day before the new one starts.">
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="as-s" label="Shift">{(a) => <Select value={shift} onChange={(e) => setShift(e.target.value)} {...a}><Opts list={shifts} blank="Select shift" /></Select>}</Field>
            <Field id="as-f" label="Effective from">{(a) => <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} {...a} />}</Field>
          </div>
          <Field id="as-d" label="Whole department (optional)">{(a) => <Select value={dept} onChange={(e) => setDept(e.target.value)} {...a}><Opts list={departments} blank="Choose people below instead" /></Select>}</Field>
          {!dept && <div className="max-h-56 space-y-1 overflow-auto rounded-lg border border-border p-2">{roster.map((r) => (
            <label key={r.employee_id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-surface-2"><input type="checkbox" checked={sel.has(r.employee_id)} onChange={(e) => setSel((s) => { const n = new Set(s); if (e.target.checked) n.add(r.employee_id); else n.delete(r.employee_id); return n })} />{r.full_name}<span className="text-muted">{r.shift ?? 'default hours'}</span></label>))}</div>}
          <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button loading={m.isPending} disabled={!shift || (!dept && sel.size === 0)} onClick={() => m.mutate({ shift_id: shift, effective_from: from, employee_ids: [...sel], department_id: dept || null })}>Assign</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function ShiftsPage() {
  const shifts = useGet<Shift[]>('/shifts')
  const roster = useGet<RosterRow[]>('/shifts/roster')
  const [open, setOpen] = React.useState(false)
  const del = useSend<string>('DELETE', (id) => `/shifts/${id}`, { invalidate: ['/shifts'], success: 'Shift deleted' })
  return (
    <>
      <PageHeader title="Shift Planners" description="Define shifts and assign them to employees or departments." actions={<div className="flex gap-2"><AssignDialog shifts={shifts.data ?? []} roster={roster.data ?? []} /><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New shift</Button></div>} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1"><CardHeader><CardTitle>Shifts</CardTitle></CardHeader>
          {shifts.isLoading ? <CardBody><Skeleton className="h-20 w-full" /></CardBody> : shifts.isError ? <ErrorState message={errorMessage(shifts.error)} /> : !shifts.data?.length ? <EmptyState title="No shifts yet" description="Employees follow the default hours from HR Policies until you assign a shift." /> : (
            <ul className="divide-y divide-border">{shifts.data.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm"><div><p className="flex items-center gap-2 font-semibold">{s.name}{s.overnight && <Moon className="h-3.5 w-3.5 text-secondary" aria-label="Overnight" />}</p><p className="text-muted">{s.start_time} to {s.end_time} · break {s.break_minutes} min</p></div>
                <ConfirmButton label="Delete" title="Delete shift" message={`Delete ${s.name}? Shifts with assignments cannot be deleted.`} onConfirm={() => del.mutate(s.id)} /></li>))}</ul>)}</Card>
        <Card className="lg:col-span-2"><CardHeader><CardTitle>Current roster</CardTitle></CardHeader>
          {roster.isLoading ? <CardBody><Skeleton className="h-20 w-full" /></CardBody> : !roster.data?.length ? <EmptyState title="No active employees" /> : (
            <div className="max-h-[32rem] overflow-auto"><table className="w-full text-left"><thead className="sticky top-0 border-b border-border bg-surface"><tr><Th>Employee</Th><Th>Department</Th><Th>Shift</Th><Th>Since</Th></tr></thead>
              <tbody className="divide-y divide-border">{roster.data.map((r) => <tr key={r.employee_id}><Td className="font-medium">{r.full_name}</Td><Td>{r.department ?? '-'}</Td><Td>{r.shift ? <Badge tone="primary">{r.shift}</Badge> : <span className="text-muted">Default hours</span>}</Td><Td>{r.effective_from ? formatDate(r.effective_from, { dateStyle: 'medium' }) : '-'}</Td></tr>)}</tbody></table></div>)}</Card>
      </div>
      <ShiftDialog open={open} onOpenChange={setOpen} />
    </>
  )
}
