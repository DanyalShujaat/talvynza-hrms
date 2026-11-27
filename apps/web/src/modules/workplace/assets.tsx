import { useViewQuery } from '@/lib/view-state'
import { Laptop, Plus } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Card, PageHeader } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { DataTable, SlideOver, StatusText } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/menu'
import { today, useGet, useSend } from '@/lib/hooks'
import { formatDate } from '@/lib/utils'
import { Opts, type EmpRow } from '@/modules/people/employees'

interface Asset { id: string; name: string; category: string; serial_number: string | null; condition: string; status: string; purchase_date: string | null; notes: string | null; assigned_to: string | null; assigned_on: string | null }
interface MyAsset { id: string; name: string; category: string; serial_number: string | null; assigned_on: string; returned_on: string | null; condition: string }
const CONDITIONS = ['new', 'good', 'fair', 'damaged']
const day = (d: string | null) => (d ? formatDate(d, { dateStyle: 'medium' }) : '')

export function MyAssetsPage() {
  const q = useGet<MyAsset[]>('/me/assets')
  return (
    <>
      <PageHeader title="My assets" description="Company property assigned to you. Contact HR if something here is wrong." />
      <Card><DataTable rows={q.data} rowKey={(a) => a.id + a.assigned_on} query={q} empty="Nothing is assigned to you" emptyIcon={Laptop} cols={[
        { header: 'Asset', cell: (a) => <div><p className="font-medium">{a.name}</p><p className="text-xs text-muted">{a.category}</p></div> },
        { header: 'Serial number', cell: (a) => a.serial_number ?? '' },
        { header: 'Assigned', cell: (a) => day(a.assigned_on) },
        { header: 'Returned', cell: (a) => (a.returned_on ? day(a.returned_on) : <StatusText status="assigned" />) },
        { header: 'Condition', cell: (a) => <span className="capitalize">{a.condition}</span> },
      ]} /></Card>
    </>
  )
}

function AssetDialog({ asset, open, onClose }: { asset: Asset | null; open: boolean; onClose: () => void }) {
  const blank = { name: '', category: 'Laptop', serial_number: '', condition: 'good', purchase_date: '', notes: '' }
  const [f, setF] = React.useState(blank)
  React.useEffect(() => { setF(asset ? { name: asset.name, category: asset.category, serial_number: asset.serial_number ?? '', condition: asset.condition, purchase_date: asset.purchase_date ?? '', notes: asset.notes ?? '' } : blank) }, [asset, open]) // eslint-disable-line react-hooks/exhaustive-deps
  const m = useSend<Record<string, unknown>>(asset ? 'PUT' : 'POST', asset ? `/assets/${asset.id}` : '/assets', { invalidate: ['/assets'], success: asset ? 'Asset updated' : 'Asset added', onSuccess: onClose })
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={asset ? 'Edit asset' : 'Add an asset'}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="as-n" label="Name" className="sm:col-span-2">{(a) => <Input placeholder="MacBook Pro 14" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} {...a} />}</Field>
          <Field id="as-c" label="Category">{(a) => <Input list="asset-cats" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} {...a} />}</Field>
          <datalist id="asset-cats">{['Laptop', 'Phone', 'Monitor', 'Access card', 'Vehicle', 'Furniture', 'Other'].map((c) => <option key={c} value={c} />)}</datalist>
          <Field id="as-s" label="Serial number">{(a) => <Input value={f.serial_number} onChange={(e) => setF({ ...f, serial_number: e.target.value })} {...a} />}</Field>
          <Field id="as-k" label="Condition">{(a) => <Select className="capitalize" value={f.condition} onChange={(e) => setF({ ...f, condition: e.target.value })} {...a}>{CONDITIONS.map((c) => <option key={c} value={c}>{c}</option>)}</Select>}</Field>
          <Field id="as-p" label="Purchase date">{(a) => <Input type="date" value={f.purchase_date} onChange={(e) => setF({ ...f, purchase_date: e.target.value })} {...a} />}</Field>
          <Field id="as-o" label="Notes" className="sm:col-span-2">{(a) => <Input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={f.name.trim().length < 2 || f.category.trim().length < 2} onClick={() => m.mutate({ ...f, serial_number: f.serial_number || null, purchase_date: f.purchase_date || null, notes: f.notes || null })}>{asset ? 'Save' : 'Add asset'}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AssignDialog({ asset, initialEmployeeId, onClose }: { asset: Asset | null; initialEmployeeId?: string; onClose: () => void }) {
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, !!asset)
  const initialPerson = useGet<EmpRow>(`/employees/${initialEmployeeId}`, undefined, !!asset && !!initialEmployeeId)
  const [emp, setEmp] = React.useState('')
  React.useEffect(() => { if (asset) setEmp(initialEmployeeId ?? '') }, [asset?.id, initialEmployeeId])
  const [on, setOn] = React.useState(today())
  const m = useSend<Record<string, unknown>>('POST', `/assets/${asset?.id}/assign`, { invalidate: ['/assets'], success: 'Asset assigned', onSuccess: () => { onClose(); setEmp('') } })
  return (
    <Dialog open={!!asset} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Assign ${asset?.name ?? ''}`} description="The employee is notified and sees it under My assets.">
        <div className="space-y-4">
          <Field id="aa-e" label="Employee">{(a) => <Select value={emp} onChange={(e) => setEmp(e.target.value)} {...a}><Opts list={[...(initialPerson.data && !(people.data?.items ?? []).some(p => p.id === initialPerson.data?.id) ? [initialPerson.data] : []), ...(people.data?.items ?? [])].map((p) => ({ id: p.id, name: `${p.full_name} (${p.employee_code})` }))} blank="Select an employee" /></Select>}</Field>
          <Field id="aa-d" label="Assigned on">{(a) => <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={!emp} onClick={() => m.mutate({ employee_id: emp, assigned_on: on })}>Assign</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReturnDialog({ asset, onClose }: { asset: Asset | null; onClose: () => void }) {
  const [on, setOn] = React.useState(today())
  const [condition, setCondition] = React.useState('good')
  const [note, setNote] = React.useState('')
  const m = useSend<Record<string, unknown>>('POST', `/assets/${asset?.id}/return`, { invalidate: ['/assets', '/offboarding'], success: 'Asset returned', onSuccess: () => { onClose(); setNote('') } })
  return (
    <Dialog open={!!asset} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Return ${asset?.name ?? ''}`} description={asset?.assigned_to ? `Currently with ${asset.assigned_to}.` : undefined}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="ar-d" label="Returned on">{(a) => <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} {...a} />}</Field>
          <Field id="ar-c" label="Condition on return">{(a) => <Select className="capitalize" value={condition} onChange={(e) => setCondition(e.target.value)} {...a}>{CONDITIONS.map((c) => <option key={c} value={c}>{c}</option>)}</Select>}</Field>
          <Field id="ar-n" label="Note (optional)" className="sm:col-span-2">{(a) => <Input value={note} onChange={(e) => setNote(e.target.value)} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} onClick={() => m.mutate({ returned_on: on, condition, note: note || null })}>Record return</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface Hist { employee: string | null; assigned_on: string; returned_on: string | null; condition_out: string; condition_in: string | null; note: string | null }
function HistoryPanel({ asset, onClose }: { asset: Asset | null; onClose: () => void }) {
  const q = useGet<Hist[]>(`/assets/${asset?.id}/history`, undefined, !!asset)
  return (
    <SlideOver open={!!asset} onOpenChange={(o) => !o && onClose()} title={`History of ${asset?.name ?? ''}`}>
      <DataTable rows={q.data} rowKey={(h) => h.assigned_on + h.employee} query={q} empty="This asset has never been assigned" cols={[
        { header: 'Employee', cell: (h) => <span className="font-medium">{h.employee}</span> },
        { header: 'From', cell: (h) => day(h.assigned_on) }, { header: 'To', cell: (h) => (h.returned_on ? day(h.returned_on) : 'Present') },
        { header: 'Condition', cell: (h) => <span className="capitalize">{h.condition_out}{h.condition_in && ` to ${h.condition_in}`}</span> },
      ]} />
    </SlideOver>
  )
}

export function AssetsPage() {
  const [sp, update] = useViewQuery()
  const initialEmployeeId = sp.get('employee_id') ?? ''
  const holderId = sp.get('holder_id')
  const requestedStatus = sp.get('status')
  const status = requestedStatus === 'all' ? '' : requestedStatus ?? (initialEmployeeId ? 'available' : '')
  const q = useGet<Asset[]>('/assets', { status: status || undefined, holder_id: holderId || undefined })
  const [editing, setEditing] = React.useState<Asset | null>(null)
  const [adding, setAdding] = React.useState(false)
  const [assigning, setAssigning] = React.useState<Asset | null>(null)
  const [returning, setReturning] = React.useState<Asset | null>(null)
  const [history, setHistory] = React.useState<Asset | null>(null)
  const setState = useSend<{ id: string; status: string }>('POST', (b) => `/assets/${b.id}/status`, { invalidate: ['/assets'], success: 'Status updated' })
  return (
    <>
      <PageHeader title="Assets" description={initialEmployeeId ? 'Choose an available asset to assign to the employee you are onboarding.' : 'Company property, who has it and its full assignment history.'} actions={<Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" />Add asset</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3"><Select aria-label="Filter by status" className="w-44" disabled={!!holderId} value={holderId ? 'assigned' : status} onChange={(e) => update({ status: e.target.value || 'all' })}>{[['', 'All assets'], ['available', 'Available'], ['assigned', 'Assigned'], ['maintenance', 'In maintenance'], ['retired', 'Retired']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>{holderId && <Button variant="ghost" onClick={() => update({ holder_id: null, status: null })}>Show all employees’ assets</Button>}</div>
      <Card><DataTable rows={q.data} rowKey={(a) => a.id} query={q} empty={holderId ? 'No assets assigned to this employee' : status ? 'No assets match this status' : 'No assets yet'} emptyHint={!holderId && !status ? 'Add laptops, phones, access cards and other company property to track who holds them.' : undefined} emptyIcon={Laptop} cols={[
        { header: 'Asset', cell: (a) => <div><p className="font-semibold">{a.name}</p><p className="text-xs text-muted">{a.category}{a.serial_number && ` · ${a.serial_number}`}</p></div> },
        { header: 'Condition', cell: (a) => <span className="capitalize">{a.condition}</span> },
        { header: 'Held by', cell: (a) => (a.assigned_to ? <div><p className="font-medium">{a.assigned_to}</p><p className="text-xs text-muted">since {day(a.assigned_on)}</p></div> : <span className="text-subtle">Nobody</span>) },
        { header: 'Status', cell: (a) => <StatusText status={a.status} /> },
        { header: '', right: true, cell: (a) => (
          <div className="flex justify-end gap-2">
            {a.status === 'available' && <Button size="sm" onClick={() => setAssigning(a)}>Assign</Button>}
            {a.status === 'assigned' && <Button size="sm" variant="outline" onClick={() => setReturning(a)}>Return</Button>}
            <Menu><MenuTrigger asChild><Button size="sm" variant="ghost">More</Button></MenuTrigger>
              <MenuContent>
                <MenuItem onSelect={() => setHistory(a)}>Assignment history</MenuItem><MenuItem onSelect={() => setEditing(a)}>Edit details</MenuItem>
                {a.status === 'available' && <MenuItem onSelect={() => setState.mutate({ id: a.id, status: 'maintenance' })}>Send to maintenance</MenuItem>}
                {a.status === 'maintenance' && <MenuItem onSelect={() => setState.mutate({ id: a.id, status: 'available' })}>Back in service</MenuItem>}
                {['available', 'maintenance'].includes(a.status) && <MenuItem onSelect={() => setState.mutate({ id: a.id, status: 'retired' })}>Retire</MenuItem>}
              </MenuContent></Menu>
          </div>) },
      ]} /></Card>
      <AssetDialog asset={editing} open={adding || !!editing} onClose={() => { setAdding(false); setEditing(null) }} />
      <AssignDialog asset={assigning} initialEmployeeId={initialEmployeeId} onClose={() => setAssigning(null)} /><ReturnDialog asset={returning} onClose={() => setReturning(null)} /><HistoryPanel asset={history} onClose={() => setHistory(null)} />
    </>
  )
}
