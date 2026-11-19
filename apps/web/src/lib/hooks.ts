import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiError, api, errorMessage } from './api'

type Params = Record<string, string | number | undefined>

export const useGet = <T,>(path: string, params?: Params, enabled = true) =>
  useQuery({ queryKey: [path, params ?? {}], queryFn: () => api<T>(path, { params }), enabled })

/** Mutation with toast feedback and cache invalidation by path prefix. */
export function useSend<TBody = unknown, TResult = unknown>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string | ((b: TBody) => string),
  opts: { invalidate?: string[]; success?: string; onSuccess?: (r: TResult, b: TBody) => void } = {},
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TBody) => api<TResult>(typeof path === 'function' ? path(body) : path, { method, body: method === 'DELETE' ? undefined : body }),
    onSuccess: (r, b) => {
      for (const k of opts.invalidate ?? []) qc.invalidateQueries({ predicate: (q) => String((q.queryKey as QueryKey)[0]).startsWith(k) })
      qc.invalidateQueries({ queryKey: ['/notifications'] }) // an action may have produced a notification
      qc.invalidateQueries({ queryKey: ['/dashboard/stats'] })
      if (opts.success) toast.success(opts.success)
      opts.onSuccess?.(r, b)
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
}

export async function uploadFile<T>(path: string, form: FormData): Promise<T> {
  const csrf = document.cookie.split('; ').find((c) => c.startsWith('nx_csrf='))?.split('=')[1] ?? ''
  const res = await fetch(`/api/v1${path}`, { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrf }, body: form })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? 'error', data?.error?.message ?? 'Upload failed', data?.error?.details)
  return data as T
}

export const money = (v: string | number | null | undefined, currency = '') =>
  v === null || v === undefined ? '-' : `${currency ? currency + ' ' : ''}${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export const hhmm = (mins: number) => `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m`
export const timeOf = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-')
export const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
