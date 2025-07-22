import React, { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Spin } from 'antd'
import { selectIsAuthenticated } from '@/store/auth/authSelectors'
import { loginSuccess } from '@/store/auth/authSlice'
import { getAuthData, migrateFromLocalStorage } from '@/utils/auth'
import { ThemeProvider } from '@/context/ThemeContext'
import { AppProviders } from '@/components/common/AppProviders'
import { ThemedToaster } from '@/components/common/ThemedToaster'
import { initializeApiClient } from '@/api/init'
import AuthLayout from '@/components/layouts/AuthLayout'
import MainLayout from '@/components/layouts/MainLayout'
import LoginPage from '@/pages/LoginPage'

// Lazy load heavy pages
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ResourcesPage = lazy(() => import('@/pages/resources/ResourcesPage'))
const QueuePage = lazy(() => import('@/pages/queue/QueuePage'))
const SystemPage = lazy(() => import('@/pages/system/SystemPage'))
const ArchitecturePage = lazy(() => import('@/pages/architecture/ArchitecturePage'))
const AuditPage = lazy(() => import('@/pages/audit/AuditPage'))
const MarketplacePage = lazy(() => import('@/pages/marketplace/MarketplacePage'))

// Loading component
const PageLoader: React.FC = () => (
  <div style={{ 
    display: 'flex', 
    justifyContent: 'center', 
    alignItems: 'center', 
    minHeight: '400px' 
  }}>
    <Spin size="large" />
  </div>
)

const AppContent: React.FC = () => {
  const dispatch = useDispatch()
  const isAuthenticated = useSelector(selectIsAuthenticated)

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
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <Routes>
            {/* Auth routes */}
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<LoginPage />} />
            </Route>

            {/* Protected routes */}
            <Route
              element={
                isAuthenticated ? <MainLayout /> : <Navigate to="/login" replace />
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
        </BrowserRouter>
        <ThemedToaster />
      </AppProviders>
  )
}

const App: React.FC = () => {
  return <AppContent />
}

export default App