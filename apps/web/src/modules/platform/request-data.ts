import { useQueries } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useMe } from '@/lib/queries'

export interface RequestRecord {
  id: string; employee_id: string; employee?: string; employee_code?: string; status: string; created_at: string
  reason?: string; description?: string; subject?: string; leave_type?: string; start_date?: string; end_date?: string
  work_date?: string; requested_in?: string; requested_out?: string; amount?: string; principal?: string
  category?: string; kind?: string; days?: number; installments?: number; decision_note?: string
}
export interface RequestRow extends RequestRecord { categoryLabel: string; to: string; slug: string }
export const waiting = new Set(['pending', 'submitted', 'manager_approved', 'requested', 'open', 'in_progress'])
export const requestTitle = (r: RequestRow) => r.subject || r.leave_type || r.category || (r.categoryLabel === 'Attendance' ? 'Time adjustment request' : r.categoryLabel === 'Loan' ? 'Loan or advance request' : r.categoryLabel === 'Expense' ? 'Expense claim' : r.categoryLabel + ' request')
export const requestDetail = (r: RequestRow) => r.reason || r.description || (r.start_date ? `${r.start_date} to ${r.end_date || r.start_date}` : r.work_date || '')
export const requestTones: Record<string, string> = { Leave: 'bg-primary-soft text-primary', Attendance: 'bg-info-soft text-cyan', Expense: 'bg-success-soft text-success', Loan: 'bg-warning-soft text-warning', 'HR ticket': 'bg-surface-2 text-muted' }
export const requestKey = (r: RequestRow) => `${r.slug}:${r.id}`
export const seenStorageKey = (identityId: string | undefined, tenantId: string | undefined, own: boolean) => `talvynza-inbox-seen:${identityId || ''}:${tenantId || ''}:${own ? 'mine' : 'team'}`
export const sourceLink = (r: RequestRow) => r.categoryLabel === 'HR ticket' ? `${r.to}/${r.id}` : r.to

export function useRequestRows(own: boolean) {
  const { data: me } = useMe()
  const p = new Set(me?.permissions ?? [])
  const configs = [
    { label: 'Leave', slug: 'leave', path: '/leave/requests', to: own ? '/me/leave' : '/leave', scope: own ? 'mine' : p.has('leave.manage') ? 'all' : 'team', enabled: p.has(own ? 'leave.apply' : 'leave.approve') },
    { label: 'Attendance', slug: 'attendance', path: '/attendance/adjustments', to: own ? '/me/attendance?tab=adjust' : '/attendance?tab=approvals', scope: own ? 'mine' : p.has('attendance.manage') ? 'all' : 'team', enabled: p.has(own ? 'attendance.read_own' : 'attendance.approve') },
    { label: 'Expense', slug: 'expense', path: '/expenses', to: own ? '/me/expenses' : '/expenses', scope: own ? 'mine' : p.has('expenses.finance_approve') ? 'all' : 'team', enabled: own ? p.has('expenses.submit') : p.has('expenses.approve') || p.has('expenses.finance_approve') },
    { label: 'Loan', slug: 'loan', path: '/loans', to: own ? '/me/loans' : '/loans', scope: own ? 'mine' : 'all', enabled: p.has(own ? 'loans.request' : 'loans.manage') },
    { label: 'HR ticket', slug: 'ticket', path: '/tickets', to: own ? '/me/helpdesk' : '/helpdesk', scope: own ? 'mine' : 'all', enabled: p.has(own ? 'helpdesk.submit' : 'helpdesk.manage') },
  ]
  const queries = useQueries({ queries: configs.map(c => ({ queryKey: [c.path, { scope: c.scope }], queryFn: () => api<RequestRecord[]>(c.path, { params: { scope: c.scope } }), enabled: c.enabled })) })
  const enabled = queries.filter((_, i) => configs[i].enabled)
  const rows = queries.flatMap((q, i) => configs[i].enabled ? (q.data || []).map(r => ({ ...r, categoryLabel: configs[i].label, slug: configs[i].slug, to: configs[i].to })) : [])
    .filter(r => own || r.employee_id !== me?.employee?.id).sort((a, b) => b.created_at.localeCompare(a.created_at))
  return { rows, configs, loading: enabled.some(q => q.isLoading), failed: enabled.find(q => q.isError), refresh: () => enabled.forEach(q => q.refetch()), me, permissions: p }
}
