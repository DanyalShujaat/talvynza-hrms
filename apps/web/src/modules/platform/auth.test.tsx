import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoginPage, RegisterPage } from './auth'

const wrap = (ui: React.ReactElement) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>
)
const res = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }))

describe('auth pages', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows field-level validation errors without calling the API', async () => {
    const f = vi.spyOn(globalThis, 'fetch')
    render(wrap(<LoginPage />))
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/enter a valid email/i)).toBeInTheDocument()
    expect(f).not.toHaveBeenCalled()
  })

  it('reveals the MFA field when the API demands a code', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => res(401, { error: { code: 'mfa_required', message: 'Multi-factor code required' } }))
    render(wrap(<LoginPage />))
    await userEvent.type(screen.getByLabelText(/work email/i), 'a@b.co')
    await userEvent.type(screen.getByLabelText(/^password/i), 'whatever-123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByLabelText(/authenticator or recovery code/i)).toBeInTheDocument()
  })

  it('shows a server error message on bad credentials', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => res(401, { error: { code: 'invalid_credentials', message: 'Invalid email or password' } }))
    render(wrap(<LoginPage />))
    await userEvent.type(screen.getByLabelText(/work email/i), 'a@b.co')
    await userEvent.type(screen.getByLabelText(/^password/i), 'whatever-123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  })

  it('registers with country-derived currency and time zone, then shows the check-inbox state', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(() => res(202, { message: 'ok' }))
    render(wrap(<RegisterPage />))
    await userEvent.type(screen.getByLabelText(/your full name/i), 'Sam Tester')
    await userEvent.type(screen.getByLabelText(/work email/i), 'sam@acme.co')
    await userEvent.type(screen.getByLabelText(/^password/i), 'Correct-Horse-Battery-9')
    await userEvent.type(screen.getByLabelText(/organization name/i), 'Acme Ltd')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))
    await waitFor(() => expect(f).toHaveBeenCalled())
    const body = JSON.parse(f.mock.calls[0]![1]!.body as string)
    expect(body).toMatchObject({ country: 'PK', currency: 'PKR', timezone: 'Asia/Karachi', organization_name: 'Acme Ltd' })
    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument()
  })
})
