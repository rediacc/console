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
import LoginPage from '@/pages/LoginPage'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { getBasePath } from '@/utils/basePath'

// Lazy load heavy pages
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ResourcesPage = lazy(() => import('@/pages/resources/ResourcesPage'))
const DistributedStoragePage = lazy(() => import('@/pages/distributedStorage/DistributedStoragePage'))
const QueuePage = lazy(() => import('@/pages/queue/QueuePage'))
const SystemPage = lazy(() => import('@/pages/system/SystemPage'))
const ArchitecturePage = lazy(() => import('@/pages/architecture/ArchitecturePage'))
const AuditPage = lazy(() => import('@/pages/audit/AuditPage'))
const MarketplacePage = lazy(() => import('@/pages/marketplace/MarketplacePage'))

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
      console.log('[RedirectHandler] Redirecting to stored path:', redirectPath)
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

  useEffect(() => {
    const initialize = async () => {
      // Initialize API client with correct URL
      await initializeApiClient()
      
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

  return (
      <AppProviders>
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
                <Route path="/" element={<Navigate to="/dashboard" replace />} />

                {/* Dashboard */}
                <Route path="/dashboard" element={
                  <Suspense fallback={<PageLoader />}>
                    <DashboardPage />
                  </Suspense>
                } />

                {/* Organization */}
                <Route path="/resources" element={
                  <Suspense fallback={<PageLoader />}>
                    <ResourcesPage />
                  </Suspense>
                } />

                {/* Distributed Storage */}
                <Route path="/distributed-storage" element={
                  <Suspense fallback={<PageLoader />}>
                    <DistributedStoragePage />
                  </Suspense>
                } />

                {/* Marketplace */}
                <Route path="/marketplace" element={
                  <Suspense fallback={<PageLoader />}>
                    <MarketplacePage />
                  </Suspense>
                } />

                {/* Queue */}
                <Route path="/queue" element={
                  <Suspense fallback={<PageLoader />}>
                    <QueuePage />
                  </Suspense>
                } />

                {/* System (Users & Permissions) */}
                <Route path="/system" element={
                  <Suspense fallback={<PageLoader />}>
                    <SystemPage />
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