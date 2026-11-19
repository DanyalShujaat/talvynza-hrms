export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message)
  }
}

const csrfToken = () =>
  document.cookie
    .split('; ')
    .find((c) => c.startsWith('nx_csrf='))
    ?.split('=')[1] ?? ''

type Opts = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | undefined>
}

/** Thin fetch wrapper: cookie session (HTTP-only, set by the API) + CSRF header on unsafe methods.
 *  The tenant is never sent from here: the server derives it from the session. */
export async function api<T = unknown>(path: string, { method = 'GET', body, params }: Opts = {}): Promise<T> {
  const qs = params
    ? '?' +
      new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined)
          .map(([k, v]) => [k, String(v)]),
      )
    : ''
  const res = await fetch(`/api/v1${path}${qs}`, {
    method,
    credentials: 'include',
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(method !== 'GET' ? { 'X-CSRF-Token': csrfToken() } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const e = data?.error
    throw new ApiError(res.status, e?.code ?? 'error', e?.message ?? res.statusText, e?.details)
  }
  return data as T
}

export const errorMessage = (e: unknown) => {
  if (e instanceof ApiError) {
    if (Array.isArray(e.details) && e.details.length && typeof e.details[0] === 'string')
      return `${e.message}: ${(e.details as string[]).join(' ')}`
    return e.message
  }
  return 'Something went wrong. Please try again.'
}
