import type { AuditEntry, Me, Member, OrgDetail, Page, PermissionDef, Role, SessionInfo } from '@talvynza/shared-types'
import { useQuery } from '@tanstack/react-query'
import { ApiError, api } from './api'

export const useMe = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: () => api<Me>('/me'),
    retry: (n, e) => !(e instanceof ApiError && e.status === 401) && n < 2,
    staleTime: 30_000,
  })
export const useMembers = (page = 1) =>
  useQuery({ queryKey: ['members', page], queryFn: () => api<Page<Member>>('/members', { params: { page, page_size: 25 } }) })
export const useRoles = () => useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/roles') })
export const usePermissions = (enabled: boolean) =>
  useQuery({ queryKey: ['permissions'], queryFn: () => api<PermissionDef[]>('/permissions'), enabled })
export const useAudit = (page = 1, enabled = true) =>
  useQuery({
    queryKey: ['audit', page],
    queryFn: () => api<Page<AuditEntry>>('/audit-logs', { params: { page, page_size: 20 } }),
    enabled,
  })
export const useOrg = () => useQuery({ queryKey: ['org'], queryFn: () => api<OrgDetail>('/organization') })
export const useSessions = () => useQuery({ queryKey: ['sessions'], queryFn: () => api<SessionInfo[]>('/auth/sessions') })
