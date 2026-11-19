import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, errorMessage } from './api'

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

describe('api client', () => {
  beforeEach(() => {
    document.cookie = 'nx_csrf=tok123'
  })
  afterEach(() => vi.restoreAllMocks())

  it('sends credentials and no CSRF header on GET', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(() => json(200, { ok: 1 }))
    await api('/me')
    const [url, init] = f.mock.calls[0]!
    expect(url).toBe('/api/v1/me')
    expect(init!.credentials).toBe('include')
    expect((init!.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined()
  })

  it('echoes the CSRF cookie on unsafe methods and never sends a tenant id', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(() => json(200, {}))
    await api('/roles', { method: 'POST', body: { key: 'x' } })
    const init = f.mock.calls[0]![1]!
    const h = init.headers as Record<string, string>
    expect(h['X-CSRF-Token']).toBe('tok123')
    expect(Object.keys(h).map((k) => k.toLowerCase())).not.toContain('x-tenant-id')
  })

  it('maps the error envelope to ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => json(403, { error: { code: 'permission_denied', message: 'Nope', details: ['x'] } }))
    const err = (await api('/audit-logs').catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(403)
    expect(err.code).toBe('permission_denied')
  })

  it('handles 204 and builds query strings, skipping undefined', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(() => json(204, null))
    await expect(api('/members', { params: { page: 2, q: undefined } })).resolves.toBeUndefined()
    expect(f.mock.calls[0]![0]).toBe('/api/v1/members?page=2')
  })

  it('formats password policy details and unknown errors', () => {
    expect(errorMessage(new ApiError(422, 'weak_password', 'Password does not meet the policy', ['Too short.']))).toContain('Too short.')
    expect(errorMessage(new Error('boom'))).toMatch(/try again/i)
  })
})
