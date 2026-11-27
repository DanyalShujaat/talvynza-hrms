import { ShieldCheck } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from '@/components/ui/card'
import { ConfirmButton } from '@/components/ui/extras'
import { Checkbox, Field, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { attendanceChannels, isAttendanceChannel, type AttendanceChannel } from '@/lib/attendance'
import { useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { Opts, useOrgLists } from '@/modules/people/employees'

interface Preview {
  total: number
  enabled: number
  sample: { id: string; name: string; code: string; enabled: boolean }[]
}

export function AttendanceAccess() {
  const { branches, departments } = useOrgLists()
  const { data: me } = useMe()
  const [params, setParams] = useSearchParams()
  const branch = params.get('branch_id') ?? ''
  const department = params.get('department_id') ?? ''
  const everyone = params.get('all_employees') === 'true'
  const requested = params.get('channel')
  const channel = isAttendanceChannel(requested) ? requested : 'web'
  const setting = attendanceChannels[channel]
  const canReadEmployees = me?.permissions.includes('employees.read')
  const premisesPath = branch && !everyone ? `/branches?premises=${branch}` : '/branches'
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const scope = everyone ? { all_employees: 'true' } : { branch_id: branch || undefined, department_id: department || undefined }
  const selected = everyone || !!branch || !!department
  const q = useGet<Preview>('/attendance/access', { ...scope, channel }, selected)
  const save = useSend<{ channel: AttendanceChannel; enabled: boolean; all_employees?: boolean; branch_id?: string; department_id?: string }, { changed: number }>(
    'PATCH', '/attendance/access', { invalidate: ['/attendance'], onSuccess: ({ changed }) => {
      toast.info(changed === 1 ? 'Attendance updated for 1 employee' : `Attendance updated for ${changed} employees`)
    } },
  )
  const update = (enabled: boolean) => save.mutate(everyone
    ? { all_employees: true, enabled, channel }
    : { branch_id: branch || undefined, department_id: department || undefined, enabled, channel })
  const data = q.data
  return (
    <div className="max-w-4xl space-y-4">
      <Card>
        <CardHeader><CardTitle>Attendance methods</CardTitle>{me?.permissions.includes('org.manage') && (
          <Button asChild variant="outline" size="sm"><Link to={premisesPath}>Manage branch premises</Link></Button>
        )}</CardHeader>
        <CardBody className="space-y-4">
          <Field id="access-channel" label="Attendance method" hint={setting.description}>{a => <Select {...a} value={channel} onChange={e => setFilter('channel', e.target.value)}>
            {Object.entries(attendanceChannels).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
          </Select>}</Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="access-branch" label="Branch">{a => <Select {...a} value={branch} disabled={everyone} onChange={e => setFilter('branch_id', e.target.value)}><Opts list={branches} blank="Any branch" /></Select>}</Field>
            <Field id="access-department" label="Department">{a => <Select {...a} value={department} disabled={everyone} onChange={e => setFilter('department_id', e.target.value)}><Opts list={departments} blank="Any department" /></Select>}</Field>
          </div>
          <Checkbox label="Select the whole organization" checked={everyone} onChange={e => setFilter('all_employees', e.target.checked ? 'true' : '')} />
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <div><CardTitle>Employees in scope</CardTitle>{data && <p className="mt-1 text-xs text-muted">{data.total} matched · {data.enabled} enabled · {data.total - data.enabled} disabled</p>}</div>
          {!!data?.total && <div className="flex flex-wrap gap-2">
            {data.enabled < data.total && <ConfirmButton label="Enable attendance" title={`Enable ${setting.label.toLowerCase()}?`}
              message={`This updates ${data.total - data.enabled} employees. ${setting.description}`}
              confirmLabel="Enable" variant="primary" loading={save.isPending} onConfirm={() => update(true)} />}
            {data.enabled > 0 && <ConfirmButton label="Disable attendance" title={`Disable ${setting.label.toLowerCase()}?`}
              message={`This turns off the selected method for ${data.enabled} employees.`}
              confirmLabel="Disable" loading={save.isPending} onConfirm={() => update(false)} />}
          </div>}
        </CardHeader>
        {!selected ? <EmptyState icon={ShieldCheck} title="Choose which employees to update" />
          : q.isPending ? <CardBody><Skeleton className="h-24" /></CardBody>
            : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} />
              : !data?.total ? <EmptyState title="No employees match these filters" />
                : <>
                  <ul className="divide-y divide-border">{data.sample.map(e => (
                    <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
                      <span className="text-sm font-semibold">{canReadEmployees ? <Link className="text-primary hover:underline" to={`/employees/${e.id}?tab=attendance`} state={{ profileBack: { to: `/attendance?${params}`, label: 'Attendance access' } }}>{e.name}</Link> : e.name} <span className="font-normal text-muted">· {e.code}</span></span>
                      <Badge tone={e.enabled ? 'success' : 'neutral'}>{e.enabled ? 'Enabled' : 'Disabled'}</Badge>
                    </li>
                  ))}</ul>
                  {data.total > data.sample.length && <p className="border-t border-border px-5 py-3 text-xs text-muted">Showing {data.sample.length} of {data.total} matching employees. The change applies to the full selection.</p>}
                </>}
      </Card>
    </div>
  )
}
