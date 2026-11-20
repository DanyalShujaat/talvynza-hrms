import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, Check, ChevronDown, ChevronsUpDown, CircleHelp, Inbox, LogOut, Menu as MenuIcon, Monitor, Moon, Plus,
  Search, ShieldCheck, Sun, UserRound,
} from 'lucide-react'
import * as React from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ErrorState, Skeleton } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Avatar } from '@/components/ui/extras'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { ApiError, api, errorMessage } from '@/lib/api'
import { useMe } from '@/lib/queries'
import { cn } from '@/lib/utils'
import { useUi } from '@/stores/ui'
import { CommandPalette } from './CommandPalette'
import { ADMIN, MY_SPACE, allowedPath, hasAdminSide, isMySpace, visibleGroups } from './nav'
import { LandingPage } from '@/modules/platform/landing'
import { guideFor } from './guides'
import { ModuleWalkthrough } from './ModuleWalkthrough'
import { Notifications } from './Notifications'

const TaliAssistant = React.lazy(() => import('@/components/assistant/TaliAssistant').then(module => ({ default: module.TaliAssistant })))

export function Brand({ compact }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5" aria-label="Talvynza HRMS home">
      <img src="/logo-mark.png" alt="" className="h-8 w-8 shrink-0" />
      {!compact && (
        <span className="leading-none">
          <span className="block font-display text-[17px] font-extrabold tracking-tight text-fg">Talvynza</span>
          <span className="brand-text text-[10px] font-bold tracking-[0.22em]">HRMS</span>
        </span>
      )}
    </Link>
  )
}
function ThemeMenu() {
  const { theme, setTheme } = useUi()
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor
  return (
    <Menu>
      <MenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Change theme"><Icon className="h-[18px] w-[18px]" /></Button></MenuTrigger>
      <MenuContent className="min-w-40">
        {(['light', 'dark', 'system'] as const).map((t) => (
          <MenuItem key={t} onSelect={() => setTheme(t)} className="capitalize">{t}{theme === t && <Check className="ml-auto h-4 w-4 text-primary" />}</MenuItem>
        ))}
      </MenuContent>
    </Menu>
  )
}

function OrgSwitcher({ compact }: { compact: boolean }) {
  const { data: me } = useMe()
  const qc = useQueryClient()
  const nav = useNavigate()
  const switchOrg = useMutation({
    mutationFn: (tenant_id: string) => api('/me/switch-organization', { method: 'POST', body: { tenant_id } }),
    onSuccess: async () => { qc.clear(); await qc.invalidateQueries(); nav('/') },
    onError: (e) => toast.error(errorMessage(e)),
  })
  if (!me) return null
  const active = me.active_organization
  return (
    <Menu>
      <MenuTrigger asChild>
        <button aria-label="Switch organization" className={cn('flex w-full cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-surface-2/60 p-2 text-left hover:bg-surface-2', compact && 'justify-center')}>
          <span className="brand-gradient flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-white"><Building2 className="h-4 w-4" /></span>
          {!compact && <><span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold">{active?.name ?? 'Select organization'}</span><span className="block truncate text-[11px] capitalize text-muted">{active ? `${active.plan_code} plan` : ''}</span></span><ChevronsUpDown className="h-4 w-4 shrink-0 text-subtle" /></>}
        </button>
      </MenuTrigger>
      <MenuContent className="min-w-64" align="start">
        <MenuLabel>Organizations</MenuLabel>
        {me.organizations.map((o) => (
          <MenuItem key={o.tenant_id} disabled={o.status === 'suspended'} onSelect={() => o.tenant_id !== active?.id && switchOrg.mutate(o.tenant_id)}>
            <span className="truncate">{o.name}</span>{o.tenant_id === active?.id && <Check className="ml-auto h-4 w-4 text-primary" />}
          </MenuItem>
        ))}
        <MenuSeparator />
        <MenuItem onSelect={() => nav('/organizations/new')}><Plus className="h-4 w-4" />New organization</MenuItem>
      </MenuContent>
    </Menu>
  )
}

function UserMenu() {
  const { data: me } = useMe()
  const qc = useQueryClient()
  const nav = useNavigate()
  const logout = useMutation({ mutationFn: () => api('/auth/logout', { method: 'POST' }), onSettled: () => { qc.clear(); nav('/login') } })
  if (!me) return null
  return (
    <Menu>
      <MenuTrigger asChild>
        <button className="flex cursor-pointer items-center gap-2 rounded-full p-0.5 pr-1.5 hover:bg-surface-2" aria-label="Account menu">
          <Avatar name={me.identity.full_name} size="sm" className="h-8 w-8" /><ChevronDown className="hidden h-3.5 w-3.5 text-subtle sm:block" />
        </button>
      </MenuTrigger>
      <MenuContent className="min-w-60">
        <div className="px-2.5 py-2">
          <p className="truncate text-sm font-semibold">{me.identity.full_name}</p>
          <p className="truncate text-xs text-muted">{me.employee?.designation ?? me.identity.email}</p>
        </div>
        <MenuSeparator />
        {me.employee && <MenuItem onSelect={() => nav('/me/profile')}><UserRound className="h-4 w-4 text-muted" />My profile</MenuItem>}
        <MenuItem onSelect={() => nav(me.employee ? '/me/security' : '/settings/security')}><ShieldCheck className="h-4 w-4 text-muted" />Security</MenuItem>
        <MenuSeparator />
        <MenuItem onSelect={() => logout.mutate()}><LogOut className="h-4 w-4 text-muted" />Sign out</MenuItem>
      </MenuContent>
    </Menu>
  )
}

function ViewSwitch({ mine, compact }: { mine: boolean; compact: boolean }) {
  if (compact) return null
  const item = (active: boolean) => cn('flex-1 rounded-md py-1.5 text-center text-[13px] font-medium transition-colors', active ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg')
  return (
    <div className="flex rounded-lg bg-surface-2 p-1" role="group" aria-label="Switch view">
      <Link to="/me" className={item(mine)} aria-current={mine ? 'page' : undefined}>My Space</Link>
      <Link to="/" className={item(!mine)} aria-current={!mine ? 'page' : undefined}>Admin</Link>
    </div>
  )
}

function Sidebar({ compact, onNavigate }: { compact: boolean; onNavigate?: () => void }) {
  const { data: me } = useMe()
  const { pathname } = useLocation()
  const perms = new Set(me?.permissions ?? [])
  const mine = isMySpace(pathname)
  const admin = hasAdminSide(perms)
  const groups = visibleGroups(mine && me?.employee ? MY_SPACE : ADMIN, perms)
  return (
    <>
      <div className="space-y-3 border-b border-border p-3">
        <OrgSwitcher compact={compact} />
        {admin && me?.employee && <ViewSwitch mine={mine} compact={compact} />}
      </div>
      <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto p-3">
        {groups.map((g) => (
          <div key={g.label}>
            {!compact && <p className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-subtle">{g.label}</p>}
            <div className="space-y-0.5">
              {g.items.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} onClick={onNavigate} title={compact ? n.label : undefined}
                  className={({ isActive }) => cn('group relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] font-medium text-muted transition-colors hover:bg-surface-2 hover:text-fg',
                    isActive && 'bg-primary-soft text-primary hover:bg-primary-soft hover:text-primary', compact && 'justify-center px-0')}>
                  {({ isActive }) => (<>
                    {isActive && !compact && <span className="brand-gradient absolute -left-3 top-1.5 h-6 w-1 rounded-r-full" aria-hidden />}
                    <n.icon className="h-[17px] w-[17px] shrink-0" aria-hidden /><span className={cn('truncate', compact && 'sr-only')}>{n.label}</span>
                  </>)}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </>
  )
}

export function AppShell() {
  const { data: me, error, isLoading, refetch } = useMe()
  const navigate = useNavigate()
  const [drawer, setDrawer] = React.useState(false)
  const [palette, setPalette] = React.useState(false)
  const [help, setHelp] = React.useState(false)
  const [guideStep, setGuideStep] = React.useState(0)
  const { pathname } = useLocation()
  const moduleGuide = guideFor(pathname)
  const guideKey = me?.identity?.id && me.active_organization?.id && moduleGuide ? `talvynza-guide-v2:${me.identity.id}:${me.active_organization.id}:${moduleGuide.title}` : null
  React.useEffect(() => {
    setGuideStep(0)
    setHelp(false)
    if (!guideKey || localStorage.getItem(guideKey) === 'seen') return
    const main = document.getElementById('main')
    if (!main) return
    const observer = new MutationObserver(() => {
      if (main.querySelector('[data-tour="page-header"], h1')) { observer.disconnect(); setHelp(true) }
    })
    observer.observe(main, { childList: true, subtree: true })
    if (main.querySelector('[data-tour="page-header"], h1')) { observer.disconnect(); setHelp(true) }
    return () => observer.disconnect()
  }, [guideKey])
  const closeGuide = () => { if (guideKey) localStorage.setItem(guideKey, 'seen'); setHelp(false) }

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(true) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  React.useEffect(() => { setDrawer(false); window.scrollTo(0, 0) }, [pathname])

  if (error instanceof ApiError && error.status === 401) return pathname === '/' ? <LandingPage /> : <Navigate to="/login" replace state={{ from: pathname }} />
  if (error) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
  if (isLoading || !me) return <div className="space-y-4 p-8"><Skeleton className="h-10 w-64" /><Skeleton className="h-64 w-full" /></div>
  if (!me.active_organization && pathname !== '/organizations/new') return <Navigate to="/organizations/new" replace />

  const perms = new Set(me.permissions)
  const currentGroups = visibleGroups(isMySpace(pathname) && me.employee ? MY_SPACE : ADMIN, perms)
  const currentGroup = currentGroups.find(g => g.items.some(i => pathname === i.to || (i.to !== '/' && pathname.startsWith(i.to + '/'))))
  const currentItem = currentGroups.flatMap(g => g.items).sort((a, b) => b.to.length - a.to.length).find(i => pathname === i.to || (i.to !== '/' && pathname.startsWith(i.to + '/')))
  // People with nothing to manage land on their own space. People without an employee record only have the admin side.
  if (pathname === '/' && me.employee && !hasAdminSide(perms)) return <Navigate to="/me" replace />
  if (isMySpace(pathname) && !me.employee && me.active_organization) return <Navigate to="/" replace />

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:shadow-pop">Skip to content</a>

      <aside data-tour="sidebar" className="no-print fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-border bg-surface md:flex">
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4"><Brand /></div>
        <Sidebar compact={false} />
      </aside>

      <Dialog open={drawer} onOpenChange={setDrawer}><DialogContent title="Navigation" className="left-0 top-0 h-dvh max-h-dvh w-72 max-w-[85vw] translate-x-0 translate-y-0 rounded-none p-0 [&>h2]:sr-only [&>div]:mt-0 [&>div]:flex [&>div]:h-full [&>div]:flex-col"><div className="flex h-14 shrink-0 items-center border-b border-border px-4"><Brand /></div><Sidebar compact={false} onNavigate={() => setDrawer(false)} /></DialogContent></Dialog>

      <div className="md:pl-64">
        <header className="no-print sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-border bg-surface/85 px-3 backdrop-blur sm:px-5">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setDrawer(true)} aria-label="Open navigation"><MenuIcon className="h-5 w-5" /></Button>
          <div className="md:hidden"><Brand compact /></div>
          <button onClick={() => setPalette(true)} className="ml-1 flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-lg border border-border bg-surface-2/60 text-sm text-subtle hover:border-border-strong sm:w-full sm:max-w-sm sm:justify-start sm:px-3" aria-label="Search">
            <Search className="h-4 w-4 shrink-0" /><span className="hidden flex-1 truncate text-left sm:block">Search pages and people</span>
            <kbd className="hidden rounded border border-border bg-surface px-1.5 font-sans text-[11px] text-muted sm:block">Ctrl K</kbd>
          </button>
          <div className="ml-auto flex shrink-0 items-center gap-0.5"><span data-tour="request-inbox"><Button asChild variant="ghost" size="icon" aria-label="Request inbox" title="Request inbox"><Link to={isMySpace(pathname) ? '/me/requests' : '/inbox'}><Inbox className="h-[18px] w-[18px]" /></Link></Button></span><Notifications /><Button variant="ghost" size="icon" aria-label="Help for this module" title="Help for this module" onClick={() => { setGuideStep(0); setHelp(true) }}><CircleHelp className="h-[18px] w-[18px]" /></Button><span className="hidden sm:inline-flex"><ThemeMenu /></span><UserMenu /></div>
        </header>
        <nav aria-label="Mobile modules" className="no-print sticky top-14 z-10 flex items-center gap-2 overflow-x-auto border-b border-border bg-surface px-3 py-2 md:hidden"><select aria-label="Go to module" className="h-8 max-w-36 shrink-0 rounded-md border border-border bg-surface px-2 text-xs font-semibold" value={currentItem?.to ?? ''} onChange={e => navigate(e.target.value)}><option value="" disabled>Choose module</option>{currentGroups.map(g => <optgroup key={g.label} label={g.label}>{g.items.map(i => <option key={i.to} value={i.to}>{i.label}</option>)}</optgroup>)}</select>{currentGroup?.items.map(i => <Link key={i.to} to={i.to} className={cn('shrink-0 rounded-md px-3 py-1.5 text-xs font-medium', pathname === i.to ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-surface-2')}>{i.label}</Link>)}</nav>
        <main id="main" className="mx-auto max-w-[1400px] p-4 sm:p-6 lg:p-8">{allowedPath(pathname, perms) ? <React.Suspense fallback={<div role="status" className="space-y-4" aria-label="Loading module"><Skeleton className="h-10 w-64" /><Skeleton className="h-48 w-full rounded-xl" /></div>}><Outlet /></React.Suspense> : <div className="rounded-xl border border-border bg-surface p-10 text-center"><ShieldCheck className="mx-auto mb-4 h-10 w-10 text-muted" /><h1 className="text-xl font-bold">This page needs a different role</h1><p className="my-3 text-muted">Your account does not have access to this area. Contact your HR administrator if you need it.</p><Button asChild><Link to={me.employee ? '/me' : '/'}>Back to my workspace</Link></Button></div>}</main>
      </div>
      {help && moduleGuide && allowedPath(pathname, perms) && <ModuleWalkthrough guide={moduleGuide} step={guideStep} onStep={setGuideStep} onClose={closeGuide} />}
      <CommandPalette open={palette} onOpenChange={setPalette} />
      {!help && !palette && !drawer && <React.Suspense fallback={null}><TaliAssistant /></React.Suspense>}
    </div>
  )
}
