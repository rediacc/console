import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { ConfigProvider, theme } from 'antd'
import { selectIsAuthenticated } from '@/store/auth/authSelectors'
import { loginSuccess } from '@/store/auth/authSlice'
import { getAuthData, migrateFromLocalStorage } from '@/utils/auth'
import { ThemeProvider, useTheme } from '@/context/ThemeContext'
import { ThemedToaster } from '@/components/common/ThemedToaster'
import AuthLayout from '@/components/layouts/AuthLayout'
import MainLayout from '@/components/layouts/MainLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import ResourcesPage from '@/pages/resources/ResourcesPage'
import QueuePage from '@/pages/queue/QueuePage'
import SystemPage from '@/pages/system/SystemPage'
import ArchitecturePage from '@/pages/architecture/ArchitecturePage'
import AuditPage from '@/pages/audit/AuditPage'

const AppContent: React.FC = () => {
  const { theme: currentTheme } = useTheme()
  const dispatch = useDispatch()
  const isAuthenticated = useSelector(selectIsAuthenticated)

  useEffect(() => {
    // Migrate any existing localStorage data to secure memory storage
    migrateFromLocalStorage()
    
    // Check for existing auth data on mount
    const authData = getAuthData()
    if (authData.token && authData.email) {
      dispatch(loginSuccess({
        user: { email: authData.email, company: authData.company || undefined },
        token: authData.token,
        company: authData.company || undefined,
      }))
    }
  }, [dispatch])

  return (
      <ConfigProvider
        theme={{
          algorithm: currentTheme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: '#333333',
            borderRadius: 6,
            colorBgContainer: currentTheme === 'dark' ? '#1a1a1a' : '#ffffff',
            colorBgElevated: currentTheme === 'dark' ? '#2a2a2a' : '#ffffff',
            colorBgLayout: currentTheme === 'dark' ? '#0a0a0a' : '#f5f5f5',
            colorText: currentTheme === 'dark' ? '#fafafa' : '#09090b',
            colorTextSecondary: currentTheme === 'dark' ? '#a1a1aa' : '#6c757d',
            colorBorder: currentTheme === 'dark' ? '#3f3f46' : '#dee2e6',
            colorBorderSecondary: currentTheme === 'dark' ? '#27272a' : '#e9ecef',
          },
        }}
      >
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
              <Route path="/dashboard" element={<DashboardPage />} />
              
              {/* Organization */}
              <Route path="/resources" element={<ResourcesPage />} />
              
              {/* Queue */}
              <Route path="/queue" element={<QueuePage />} />
              
              {/* System (Users & Permissions) */}
              <Route path="/system" element={<SystemPage />} />
              
              {/* Audit */}
              <Route path="/audit" element={<AuditPage />} />
              
              {/* Architecture */}
              <Route path="/architecture" element={<ArchitecturePage />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <ThemedToaster />
      </ConfigProvider>
  )
}

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}

export default App