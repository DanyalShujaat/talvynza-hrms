import { useViewTab } from '@/lib/view-state'
import { BarChart3, Download } from 'lucide-react'
import * as React from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { DataTable, Progress, Tabs, downloadCsv } from '@/components/ui/extras'
import { Input } from '@/components/ui/form'
import { money, today, useGet } from '@/lib/hooks'
import { useMe } from '@/lib/queries'

interface Group { label: string; count: number }
interface Headcount { total: number; by_department: Group[]; by_branch: Group[]; by_status: Group[]; by_employment_type: Group[]; movement: { month: string; joined: number; left: number }[] }
interface AttRow { employee_id: string; employee_code: string; employee: string; department: string | null; working_days: number; present_days: number; leave_days: number; absent_days: number; late_days: number; late_minutes: number; worked_hours: number; overtime_hours: number }
interface LeaveRow { employee_code: string; employee: string; department: string | null; leave_type: string; entitled: string; used: string; pending: string; available: string }
interface Payroll { currency: string; runs: { month: string; period: string; employees: number; gross: string; deductions: string; income_tax: string; net: string }[]; by_department: { department: string; gross: string; net: string }[] }

const tip = { background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 10, fontSize: 13 }
const axis = { fontSize: 12, fill: 'var(--color-muted)' }

function Breakdown({ title, rows }: { title: string; rows: Group[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <Card><CardHeader><CardTitle>{title}</CardTitle></CardHeader><CardBody className="space-y-2.5">
      {rows.length === 0 && <p className="text-sm text-muted">No data.</p>}
      {rows.map((r) => <div key={r.label} className="flex items-center gap-3 text-sm"><span className="w-36 truncate capitalize">{r.label.replace(/_/g, ' ')}</span><Progress value={(r.count / max) * 100} className="flex-1" /><span className="w-8 text-right font-semibold tabular-nums">{r.count}</span></div>)}
    </CardBody></Card>
  )
}

function HeadcountReport() {
  const q = useGet<Headcount>('/reports/headcount')
  if (q.isError) return <Card><ErrorState message="Headcount could not be loaded." onRetry={() => q.refetch()} /></Card>
  if (!q.data) return <Skeleton className="h-64 w-full rounded-xl" />
  const d = q.data
  return (
    <div className="space-y-6">
      <Card><CardHeader><CardTitle>Joiners and leavers, last 12 months</CardTitle><span className="text-sm text-muted">{d.total} current employees</span></CardHeader><CardBody>
        <div className="h-60" role="img" aria-label="Employees who joined and left in each of the last twelve months"><ResponsiveContainer width="100%" height="100%">
          <BarChart data={d.movement.map((m) => ({ ...m, label: new Date(m.month + '-01T00:00:00').toLocaleDateString(undefined, { month: 'short' }) }))} margin={{ left: -22, top: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--color-border)" /><XAxis dataKey="label" tickLine={false} axisLine={false} tick={axis} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={axis} />
            <Tooltip cursor={{ fill: 'var(--color-surface-2)' }} contentStyle={tip} />
            <Bar dataKey="joined" name="Joined" fill="#0f4bb5" radius={[3, 3, 0, 0]} maxBarSize={22} /><Bar dataKey="left" name="Left" fill="#d02b49" radius={[3, 3, 0, 0]} maxBarSize={22} />
          </BarChart></ResponsiveContainer></div>
      </CardBody></Card>
      <div className="grid gap-6 md:grid-cols-2"><Breakdown title="By department" rows={d.by_department} /><Breakdown title="By branch" rows={d.by_branch} /><Breakdown title="By status" rows={d.by_status} /><Breakdown title="By employment type" rows={d.by_employment_type} /></div>
    </div>
  )
}

function AttendanceReport() {
  const [month, setMonth] = React.useState(today().slice(0, 7))
  const q = useGet<{ rows: AttRow[] }>('/reports/attendance', { month })
  const rows = q.data?.rows
  return (
    <Card>
      <CardHeader><CardTitle>Attendance summary</CardTitle><div className="flex gap-2"><Input type="month" aria-label="Month" className="w-44" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
        <Button variant="outline" disabled={!rows?.length} onClick={() => downloadCsv(`attendance-${month}.csv`, [['Employee ID', 'Employee', 'Department', 'Working days', 'Present', 'Leave', 'Absent', 'Late days', 'Late minutes', 'Hours worked', 'Overtime hours'], ...(rows ?? []).map((r) => [r.employee_code, r.employee, r.department, r.working_days, r.present_days, r.leave_days, r.absent_days, r.late_days, r.late_minutes, r.worked_hours, r.overtime_hours])])}><Download className="h-4 w-4" />Export CSV</Button></div></CardHeader>
      <DataTable rows={rows} rowKey={(r) => r.employee_id} query={q} empty="No employees to report on" cols={[
        { header: 'Employee', cell: (r) => <div><p className="font-medium">{r.employee}</p><p className="text-xs text-muted">{r.employee_code}{r.department && ` · ${r.department}`}</p></div> },
        { header: 'Working days', right: true, cell: (r) => r.working_days }, { header: 'Present', right: true, cell: (r) => r.present_days }, { header: 'Leave', right: true, cell: (r) => r.leave_days },
        { header: 'Absent', right: true, cell: (r) => <span className={r.absent_days ? 'font-semibold text-danger' : ''}>{r.absent_days}</span> },
        { header: 'Late days', right: true, cell: (r) => <span className={r.late_days ? 'font-medium text-warning' : ''}>{r.late_days}</span> },
        { header: 'Hours', right: true, cell: (r) => r.worked_hours }, { header: 'Overtime', right: true, cell: (r) => r.overtime_hours },
      ]} />
    </Card>
  )
}

function LeaveReport() {
  const [year, setYear] = React.useState(new Date().getFullYear())
  const q = useGet<{ rows: LeaveRow[] }>('/reports/leave', { year })
  const rows = q.data?.rows
  return (
    <Card>
      <CardHeader><CardTitle>Leave balances</CardTitle><div className="flex gap-2"><Input type="number" aria-label="Year" className="w-28" value={year} onChange={(e) => setYear(Number(e.target.value))} />
        <Button variant="outline" disabled={!rows?.length} onClick={() => downloadCsv(`leave-${year}.csv`, [['Employee ID', 'Employee', 'Department', 'Leave type', 'Entitled', 'Used', 'Pending', 'Available'], ...(rows ?? []).map((r) => [r.employee_code, r.employee, r.department, r.leave_type, r.entitled, r.used, r.pending, r.available])])}><Download className="h-4 w-4" />Export CSV</Button></div></CardHeader>
      <DataTable rows={rows} rowKey={(r) => r.employee_code + r.leave_type} query={q} empty="No leave has been granted for this year" cols={[
        { header: 'Employee', cell: (r) => <div><p className="font-medium">{r.employee}</p><p className="text-xs text-muted">{r.employee_code}{r.department && ` · ${r.department}`}</p></div> },
        { header: 'Leave type', cell: (r) => r.leave_type },
        { header: 'Entitled', right: true, cell: (r) => Number(r.entitled) }, { header: 'Used', right: true, cell: (r) => Number(r.used) }, { header: 'Pending', right: true, cell: (r) => Number(r.pending) },
        { header: 'Available', right: true, cell: (r) => <span className="font-semibold">{Number(r.available)}</span> },
      ]} />
    </Card>
  )
}

function PayrollReport() {
  const [year, setYear] = React.useState(new Date().getFullYear())
  const q = useGet<Payroll>('/reports/payroll', { year })
  const d = q.data
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Finalized payroll by month</CardTitle><div className="flex gap-2"><Input type="number" aria-label="Year" className="w-28" value={year} onChange={(e) => setYear(Number(e.target.value))} />
          <Button variant="outline" disabled={!d?.runs.length} onClick={() => downloadCsv(`payroll-${year}.csv`, [['Period', 'Employees', 'Gross', 'Deductions', 'Income tax', 'Net'], ...(d?.runs ?? []).map((r) => [r.period, r.employees, r.gross, r.deductions, r.income_tax, r.net])])}><Download className="h-4 w-4" />Export CSV</Button></div></CardHeader>
        {!!d?.runs.length && <CardBody className="border-b border-border"><div className="h-56" role="img" aria-label="Net pay per month"><ResponsiveContainer width="100%" height="100%">
          <BarChart data={d.runs.map((r) => ({ month: new Date(r.month + '-01T00:00:00').toLocaleDateString(undefined, { month: 'short' }), Net: Number(r.net), Tax: Number(r.income_tax) }))} margin={{ left: 8, top: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--color-border)" /><XAxis dataKey="month" tickLine={false} axisLine={false} tick={axis} /><YAxis tickLine={false} axisLine={false} tick={axis} tickFormatter={(v) => Number(v).toLocaleString(undefined, { notation: 'compact' })} />
            <Tooltip cursor={{ fill: 'var(--color-surface-2)' }} contentStyle={tip} formatter={(v) => Number(v).toLocaleString()} />
            <Bar dataKey="Net" stackId="a" fill="#0f4bb5" maxBarSize={36} /><Bar dataKey="Tax" stackId="a" fill="#d99a1c" radius={[3, 3, 0, 0]} maxBarSize={36} />
          </BarChart></ResponsiveContainer></div></CardBody>}
        <DataTable rows={d?.runs} rowKey={(r) => r.period} query={q} empty="No finalized payroll in this year" cols={[
          { header: 'Period', cell: (r) => r.period }, { header: 'Employees', right: true, cell: (r) => r.employees },
          { header: 'Gross', right: true, cell: (r) => money(r.gross) }, { header: 'Income tax', right: true, cell: (r) => money(r.income_tax) }, { header: 'Deductions', right: true, cell: (r) => money(r.deductions) },
          { header: `Net (${d?.currency ?? ''})`, right: true, cell: (r) => <span className="font-semibold">{money(r.net)}</span> },
        ]} />
      </Card>
      {!!d?.by_department.length && <Card><CardHeader><CardTitle>Cost by department, {year}</CardTitle></CardHeader>
        <DataTable rows={d.by_department} rowKey={(r) => r.department} empty="" cols={[{ header: 'Department', cell: (r) => r.department }, { header: 'Gross', right: true, cell: (r) => money(r.gross) }, { header: 'Net', right: true, cell: (r) => <span className="font-semibold">{money(r.net)}</span> }]} /></Card>}
    </div>
  )
}

export function ReportsPage() {
  const { data: me } = useMe()
  type T = 'headcount' | 'attendance' | 'leave' | 'payroll'
  const tabs: { id: T; label: string }[] = [{ id: 'headcount', label: 'Headcount' }, { id: 'attendance', label: 'Attendance' }, { id: 'leave', label: 'Leave' }]
  if (me?.permissions.includes('payroll.read')) tabs.push({ id: 'payroll', label: 'Payroll' })
  const [tab, setTab] = useViewTab(tabs.map(item => item.id), 'headcount')
  if (!me?.permissions.includes('reports.view')) return <Card><EmptyState icon={BarChart3} title="Reports are not available for your role" /></Card>
  return (
    <>
      <PageHeader title="Reports" description="Figures are calculated from live records each time you open a report." />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'headcount' && <HeadcountReport />}{tab === 'attendance' && <AttendanceReport />}{tab === 'leave' && <LeaveReport />}{tab === 'payroll' && <PayrollReport />}
    </>
  )
}
