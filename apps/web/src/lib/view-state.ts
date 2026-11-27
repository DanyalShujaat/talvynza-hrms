import { useLocation, useSearchParams } from 'react-router-dom'
import { useCallback } from 'react'

export function useRecordFocus(recordId: string | null) {
  return useCallback((node: HTMLElement | null) => {
    if (!node || !recordId) return
    requestAnimationFrame(() => {
      if (!node.isConnected) return
      node.focus({ preventScroll: true })
      node.scrollIntoView({ block: 'nearest' })
    })
  }, [recordId])
}

export function useViewQuery() {
  const [params, setParams] = useSearchParams()
  const { state } = useLocation()
  const update = (values: Record<string, string | number | null>, replace = true) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(values)) {
      if (value == null || value === '') next.delete(key)
      else next.set(key, String(value))
    }
    setParams(next, { replace, preventScrollReset: true, state })
  }
  return [params, update] as const
}

export function useViewTab<T extends string>(choices: readonly T[], fallback: T) {
  const [params, update] = useViewQuery()
  return [choices.find(value => value === params.get('tab')) ?? fallback,
    (tab: T) => update({ tab, record: null }, false)] as const
}

const viewKeys = new Set(['tab', 'q', 'status', 'view', 'page', 'letter', 'branch_id', 'department_id',
  'month', 'date', 'year', 'scope', 'channel', 'all_employees', 'employee_id', 'import_mode',
  'job_id', 'report_job', 'stage', 'priority', 'type'])

export function rememberView(scope: string, path: string, search: string) {
  const params = new URLSearchParams(search)
  if (params.has('record')) return
  for (const key of [...params.keys()]) if (!viewKeys.has(key)) params.delete(key)
  if (['/assets', '/loans', '/expenses'].includes(path)) params.delete('employee_id')
  try { sessionStorage.setItem(`talvynza:view:${scope}:${path}`, params.toString()) } catch { /* URLs still work */ }
}

export function restoreView(scope: string | undefined, path: string) {
  if (!scope) return path
  try {
    const search = sessionStorage.getItem(`talvynza:view:${scope}:${path}`)
    return search ? `${path}?${search}` : path
  } catch { return path }
}
