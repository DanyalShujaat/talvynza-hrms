import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/layout/AppShell'
import { ApiError } from '@/lib/api'
import { LandingPage } from '@/modules/platform/landing'
import { DemoPage } from '@/modules/platform/demo'
import { ErrorBoundary } from '@/components/layout/ErrorBoundary'
import { ForgotPasswordPage, JoinPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from '@/modules/platform/auth'
import './index.css'

/** Loads one named page component from its module on first visit. */
const page = <T,>(load: () => Promise<T>, name: keyof T) =>
  lazy(() => load().then((m) => ({ default: m[name] as unknown as React.ComponentType })))

const DashboardPage = page(() => import('@/modules/platform/dashboard'), 'DashboardPage')
const MyHomePage = page(() => import('@/modules/platform/me-home'), 'MyHomePage')
const RequestsPage = lazy(() => import('@/modules/platform/requests').then(m => ({ default: m.RequestsPage })))
const RequestDetailPage = lazy(() => import('@/modules/platform/request-detail').then(m => ({ default: m.RequestDetailPage })))
const MyAttendancePage = page(() => import('@/modules/time/attendance'), 'MyAttendancePage')
const AttendancePage = page(() => import('@/modules/time/attendance'), 'AttendancePage')
const MyLeavePage = page(() => import('@/modules/time/leave'), 'MyLeavePage')
const LeaveAdminPage = page(() => import('@/modules/time/leave'), 'LeaveAdminPage')
const PayrollPage = page(() => import('@/modules/pay/payroll'), 'PayrollPage')
const PayrollRunPage = page(() => import('@/modules/pay/payroll'), 'PayrollRunPage')
const PayslipsPage = page(() => import('@/modules/pay/payroll'), 'PayslipsPage')
const MyExpensesPage = page(() => import('@/modules/pay/expenses'), 'MyExpensesPage')
const ExpensesPage = page(() => import('@/modules/pay/expenses'), 'ExpensesPage')
const MyLoansPage = page(() => import('@/modules/pay/loans'), 'MyLoansPage')
const LoansPage = page(() => import('@/modules/pay/loans'), 'LoansPage')
const MyAssetsPage = page(() => import('@/modules/workplace/assets'), 'MyAssetsPage')
const AssetsPage = page(() => import('@/modules/workplace/assets'), 'AssetsPage')
const MyHelpdeskPage = page(() => import('@/modules/workplace/helpdesk'), 'MyHelpdeskPage')
const HelpdeskPage = page(() => import('@/modules/workplace/helpdesk'), 'HelpdeskPage')
const TicketPage = lazy(() => import('@/modules/workplace/helpdesk').then((m) => ({ default: m.TicketPage })))
const MyPerformancePage = page(() => import('@/modules/workplace/performance'), 'MyPerformancePage')
const PerformancePage = page(() => import('@/modules/workplace/performance'), 'PerformancePage')
const MyTrainingPage = page(() => import('@/modules/workplace/training'), 'MyTrainingPage')
const TrainingPage = page(() => import('@/modules/workplace/training'), 'TrainingPage')
const OffboardingPage = page(() => import('@/modules/people/offboarding'), 'OffboardingPage')
const OffboardingDetailPage = page(() => import('@/modules/people/offboarding'), 'OffboardingDetailPage')
const ReportsPage = page(() => import('@/modules/platform/reports'), 'ReportsPage')
const OrgChartPage = page(() => import('@/modules/people/org-chart'), 'OrgChartPage')
const NoticesPage = lazy(() => import('@/modules/workplace/work').then((m) => ({ default: m.NoticesPage })))
const MyTasksPage = page(() => import('@/modules/workplace/tasks'), 'MyTasksPage')
const TasksPage = page(() => import('@/modules/workplace/tasks'), 'TasksPage')
const EmployeesPage = page(() => import('@/modules/people/employees'), 'EmployeesPage')
const EmployeeDetailPage = lazy(() => import('@/modules/people/employee-detail').then((m) => ({ default: m.EmployeeDetailPage })))
const DepartmentsPage = page(() => import('@/modules/organization/structure'), 'DepartmentsPage')
const BranchesPage = page(() => import('@/modules/organization/structure'), 'BranchesPage')
const PoliciesPage = page(() => import('@/modules/organization/structure'), 'PoliciesPage')
const ShiftsPage = page(() => import('@/modules/time/shifts'), 'ShiftsPage')
const HirePage = page(() => import('@/modules/recruitment/hire'), 'HirePage')
const CareersPage = page(() => import('@/modules/recruitment/hire'), 'CareersPage')
const MembersPage = page(() => import('@/modules/platform/access'), 'MembersPage')
const RolesPage = page(() => import('@/modules/platform/access'), 'RolesPage')
const AuditPage = page(() => import('@/modules/platform/access'), 'AuditPage')
const OrgSettingsPage = page(() => import('@/modules/platform/settings'), 'OrgSettingsPage')
const SecurityPage = page(() => import('@/modules/platform/settings'), 'SecurityPage')
const NewOrganizationPage = page(() => import('@/modules/platform/settings'), 'NewOrganizationPage')

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2 },
  },
})

const Loading = () => <div className="p-8 text-sm text-muted" role="status">Loading...</div>

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary><BrowserRouter>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/welcome" element={<LandingPage />} />
            <Route path="/demo" element={<DemoPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/accept-invitation" element={<JoinPage />} />
            <Route path="/careers/:slug" element={<CareersPage />} />
            <Route element={<AppShell />}>
              {/* My Space: every employee's own side */}
              <Route path="me" element={<MyHomePage />} />
              <Route path="me/requests" element={<RequestsPage own />} />
              <Route path="me/requests/:kind/:id" element={<RequestDetailPage own />} />
              <Route path="inbox" element={<RequestsPage />} />
              <Route path="inbox/:kind/:id" element={<RequestDetailPage />} />
              <Route path="me/profile" element={<EmployeeDetailPage own />} />
              <Route path="me/attendance" element={<MyAttendancePage />} />
              <Route path="me/leave" element={<MyLeavePage />} />
              <Route path="me/payslips" element={<PayslipsPage />} />
              <Route path="me/expenses" element={<MyExpensesPage />} />
              <Route path="me/loans" element={<MyLoansPage />} />
              <Route path="me/tasks" element={<MyTasksPage />} />
              <Route path="me/notices" element={<NoticesPage />} />
              <Route path="me/performance" element={<MyPerformancePage />} />
              <Route path="me/training" element={<MyTrainingPage />} />
              <Route path="me/assets" element={<MyAssetsPage />} />
              <Route path="me/helpdesk" element={<MyHelpdeskPage />} />
              <Route path="me/helpdesk/:id" element={<TicketPage />} />
              <Route path="me/security" element={<SecurityPage />} />
              {/* Admin: management side, gated by permission */}
              <Route index element={<DashboardPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="employees" element={<EmployeesPage />} />
              <Route path="employees/:id" element={<EmployeeDetailPage />} />
              <Route path="org-chart" element={<OrgChartPage />} />
              <Route path="departments" element={<DepartmentsPage />} />
              <Route path="branches" element={<BranchesPage />} />
              <Route path="hire" element={<HirePage />} />
              <Route path="offboarding" element={<OffboardingPage />} />
              <Route path="offboarding/:id" element={<OffboardingDetailPage />} />
              <Route path="attendance" element={<AttendancePage />} />
              <Route path="shifts" element={<ShiftsPage />} />
              <Route path="leave" element={<LeaveAdminPage />} />
              <Route path="payroll" element={<PayrollPage />} />
              <Route path="payroll/runs/:id" element={<PayrollRunPage />} />
              <Route path="expenses" element={<ExpensesPage />} />
              <Route path="loans" element={<LoansPage />} />
              <Route path="performance" element={<PerformancePage />} />
              <Route path="training" element={<TrainingPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="assets" element={<AssetsPage />} />
              <Route path="helpdesk" element={<HelpdeskPage />} />
              <Route path="helpdesk/:id" element={<TicketPage staff />} />
              <Route path="notices" element={<NoticesPage manage />} />
              <Route path="policies" element={<PoliciesPage />} />
              <Route path="people/members" element={<MembersPage />} />
              <Route path="access/roles" element={<RolesPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="settings/organization" element={<OrgSettingsPage />} />
              <Route path="settings/security" element={<SecurityPage />} />
              <Route path="organizations/new" element={<NewOrganizationPage />} />
              {/* Old addresses */}
              <Route path="profile" element={<Navigate to="/me/profile" replace />} />
              <Route path="payslips" element={<Navigate to="/me/payslips" replace />} />
              <Route path="applications" element={<Navigate to="/me/leave" replace />} />
              <Route path="leave-planner" element={<Navigate to="/leave" replace />} />
              <Route path="*" element={<p className="p-8 text-muted">This page does not exist.</p>} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter></ErrorBoundary>
      <Toaster richColors closeButton position="top-right" />
    </QueryClientProvider>
  )
}

const el = document.getElementById('root')
if (el) createRoot(el).render(<React.StrictMode><App /></React.StrictMode>)
