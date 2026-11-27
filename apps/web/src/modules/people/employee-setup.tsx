import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ErrorState, Notice, Skeleton } from '@/components/ui/card'
import { errorMessage } from '@/lib/api'
import { useGet } from '@/lib/hooks'
import { useMe } from '@/lib/queries'

const requirements = {
  branch: { label: 'Add an active branch', to: '/branches', permission: 'org.manage' },
  department: { label: 'Add an active department', to: '/departments', permission: 'org.manage' },
  attendance_policy: { label: 'Save the attendance policy', to: '/policies', permission: 'attendance.manage' },
  leave_type: { label: 'Add an active leave type', to: '/policies?tab=leave', permission: 'leave.manage' },
  payroll: { label: 'Create an active salary template', to: '/payroll?tab=templates', permission: 'salary.manage' },
}

export function EmployeeSetup({ children }: { children: ReactNode }) {
  const setup = useGet<{ missing: (keyof typeof requirements)[] }>('/employees/setup')
  const { data: me } = useMe()

  if (setup.isPending) return <Skeleton className="h-24 w-full" />
  if (setup.isError) return <ErrorState message={errorMessage(setup.error)} onRetry={() => setup.refetch()} />
  if (!setup.data.missing.length) return children

  return (
    <Notice tone="warning">
      <div>
        <p className="font-semibold">Complete setup before adding employees</p>
        <ul className="mt-2 list-inside list-disc space-y-1">
          {setup.data.missing.map(key => {
            const { label, to, permission } = requirements[key]
            return <li key={key}>{me?.permissions.includes(permission) ? <Link className="font-medium underline" to={to}>{label}</Link> : label}</li>
          })}
        </ul>
      </div>
    </Notice>
  )
}
