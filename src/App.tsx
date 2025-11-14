import React, { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Spin } from 'antd'
import { selectIsAuthenticated } from '@/store/auth/authSelectors'
import { RootState } from '@/store/store'
import { loginSuccess } from '@/store/auth/authSlice'
import { getAuthData, migrateFromLocalStorage } from '@/utils/auth'
import { AppProviders } from '@/components/common/AppProviders'
import { ThemedToaster } from '@/components/common/ThemedToaster'
import { SessionExpiredDialog } from '@/components/auth/SessionExpiredDialog'
import { TelemetryProvider } from '@/components/common/TelemetryProvider'
import { InteractionTracker } from '@/components/common/InteractionTracker'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { initializeApiClient } from '@/api/init'
import AuthLayout from '@/components/layouts/AuthLayout'
import MainLayout from '@/components/layouts/MainLayout'
import LoginPage from '@/pages/login'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { getBasePath } from '@/utils/basePath'
import { featureFlags } from '@/config/featureFlags'
import { GlobalStyles } from '@/styles/GlobalStyles'

// Lazy load heavy pages
const DashboardPage = lazy(() => import('@/pages/dashboard'))
const MachinesPage = lazy(() => import('@/pages/machines/MachinesPage'))
const MachineRepositoriesPage = lazy(() => import('@/pages/resources/MachineRepositoriesPage'))
const RepositoryContainersPage = lazy(() => import('@/pages/resources/RepositoryContainersPage'))
const DistributedStoragePage = lazy(() => import('@/pages/distributedStorage/DistributedStoragePage'))
const QueuePage = lazy(() => import('@/pages/queue/QueuePage'))
const ArchitecturePage = lazy(() => import('@/pages/architecture/ArchitecturePage'))
const AuditPage = lazy(() => import('@/pages/audit/AuditPage'))
const CredentialsPage = lazy(() => import('@/pages/credentials/CredentialsPage'))
const StoragePage = lazy(() => import('@/pages/storage/StoragePage'))
const UsersPage = lazy(() => import('@/pages/organization/users/UsersPage'))
const TeamsPage = lazy(() => import('@/pages/organization/teams/TeamsPage'))
const AccessPage = lazy(() => import('@/pages/organization/access/AccessPage'))
const ProfilePage = lazy(() => import('@/pages/settings/profile/ProfilePage'))
const CompanyPage = lazy(() => import('@/pages/settings/company/CompanyPage'))
const InfrastructurePage = lazy(() => import('@/pages/settings/infrastructure/InfrastructurePage'))

// Loading component
const PageLoader: React.FC = () => {
  const styles = useComponentStyles()

  return (
    <div
      data-testid="page-loader"
      style={{
        ...styles.flexCenter,
        minHeight: '400px'
      }}
    >
      <Spin size="large" />
    </div>
  )
}

// Component to handle GitHub Pages 404 redirect via sessionStorage
const RedirectHandler: React.FC = () => {
  const navigate = useNavigate()

  useEffect(() => {
    // Check if we were redirected from a 404 page
    const redirectPath = sessionStorage.getItem('redirect_path')

    if (redirectPath) {
      // Clear the redirect path immediately to prevent loops
      sessionStorage.removeItem('redirect_path')

      // Navigate to the intended path
      navigate(redirectPath, { replace: true })
    }
  }, [navigate])

  return null
}

const AppContent: React.FC = () => {
  const dispatch = useDispatch()
  const isAuthenticated = useSelector(selectIsAuthenticated)
  const showSessionExpiredDialog = useSelector((state: RootState) => state.auth.showSessionExpiredDialog)
  const stayLoggedOutMode = useSelector((state: RootState) => state.auth.stayLoggedOutMode)
  const [, setFeatureFlagVersion] = React.useState(0)

  useEffect(() => {
    const initialize = async () => {
      // Initialize API client with correct URL
      await initializeApiClient()

      // Initialize feature flags after API connection is established
      // This determines if we're in local development mode or production
      featureFlags.updateDevelopmentState()

      // Migrate any existing localStorage data to secure memory storage
      await migrateFromLocalStorage()

      // Check for existing auth data on mount
      const authData = await getAuthData()
      if (authData.token && authData.email) {
        // Token exists in secure storage, restore session (token not stored in Redux for security)
        dispatch(loginSuccess({
          user: { email: authData.email, company: authData.company || undefined },
          company: authData.company || undefined,
        }))
      }
    }

    initialize()
  }, [dispatch])

  useEffect(() => {
    const unsubscribe = featureFlags.subscribe(() => {
      setFeatureFlagVersion((version) => version + 1)
    })
    return unsubscribe
  }, [])

  return (
      <AppProviders>
        <GlobalStyles />
          <BrowserRouter basename={getBasePath()}>
            <RedirectHandler />
            <TelemetryProvider>
              <ErrorBoundary>
                <InteractionTracker>
                  <Routes>
              {/* Auth routes */}
              <Route element={<AuthLayout />}>
                <Route path="/login" element={<LoginPage />} />
              </Route>

              {/* Protected routes */}
              <Route
                element={
                  (isAuthenticated || showSessionExpiredDialog || stayLoggedOutMode) ? <MainLayout /> : <Navigate to="/login" replace />
                }
              >
                <Route path="/" element={<Navigate to="/machines" replace />} />

                {/* Dashboard */}
                <Route path="/dashboard" element={
                  <Suspense fallback={<PageLoader />}>
                    <DashboardPage />
                  </Suspense>
                } />

                {/* Organization */}
                <Route path="/machines" element={
                  <Suspense fallback={<PageLoader />}>
                    <MachinesPage />
                  </Suspense>
                } />
                <Route path="/resources" element={<Navigate to="/machines" replace />} />
                <Route path="/credentials" element={
                  <Suspense fallback={<PageLoader />}>
                    <CredentialsPage />
                  </Suspense>
                } />
                <Route path="/storage" element={
                  <Suspense fallback={<PageLoader />}>
                    <StoragePage />
                  </Suspense>
                } />

                {/* Organization redirects */}
                <Route path="/organization" element={<Navigate to="/organization/users" replace />} />
                <Route path="/settings" element={<Navigate to="/settings/profile" replace />} />

                {/* Organization */}
                <Route path="/organization/users" element={
                  <Suspense fallback={<PageLoader />}>
                    <UsersPage />
                  </Suspense>
                } />
                <Route path="/organization/teams" element={
                  <Suspense fallback={<PageLoader />}>
                    <TeamsPage />
                  </Suspense>
                } />
                <Route path="/organization/access" element={
                  <Suspense fallback={<PageLoader />}>
                    <AccessPage />
                  </Suspense>
                } />

                {/* Settings */}
                <Route path="/settings/profile" element={
                  <Suspense fallback={<PageLoader />}>
                    <ProfilePage />
                  </Suspense>
                } />
                <Route path="/settings/company" element={
                  <Suspense fallback={<PageLoader />}>
                    <CompanyPage />
                  </Suspense>
                } />
                <Route path="/settings/infrastructure" element={
                  <Suspense fallback={<PageLoader />}>
                    <InfrastructurePage />
                  </Suspense>
                } />

                {/* Machine Repositories */}
                <Route path="/machines/:machineName/repositories" element={
                  <Suspense fallback={<PageLoader />}>
                    <MachineRepositoriesPage />
                  </Suspense>
                } />

                {/* Repository Containers */}
                <Route path="/machines/:machineName/repositories/:repositoryName/containers" element={
                  <Suspense fallback={<PageLoader />}>
                    <RepositoryContainersPage />
                  </Suspense>
                } />

                {/* Distributed Storage */}
                <Route path="/distributed-storage" element={
                  <Suspense fallback={<PageLoader />}>
                    <DistributedStoragePage />
                  </Suspense>
                } />

                {/* Queue */}
                <Route path="/queue" element={
                  <Suspense fallback={<PageLoader />}>
                    <QueuePage />
                  </Suspense>
                } />

                {/* Audit */}
                <Route path="/audit" element={
                  <Suspense fallback={<PageLoader />}>
                    <AuditPage />
                  </Suspense>
                } />

                {/* Architecture */}
                <Route path="/architecture" element={
                  <Suspense fallback={<PageLoader />}>
                    <ArchitecturePage />
                  </Suspense>
                } />
              </Route>
                  </Routes>
                </InteractionTracker>
              </ErrorBoundary>
            </TelemetryProvider>
          </BrowserRouter>
          <ThemedToaster />
          <SessionExpiredDialog />
      </AppProviders>
  )
}

const App: React.FC = () => {
  return <AppContent />
}

export default App
