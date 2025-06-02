import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { ConfigProvider } from 'antd'
import { selectIsAuthenticated } from '@/store/auth/authSelectors'
import { loginSuccess } from '@/store/auth/authSlice'
import { getAuthData } from '@/utils/auth'
import AuthLayout from '@/components/layouts/AuthLayout'
import MainLayout from '@/components/layouts/MainLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import OrganizationPage from '@/pages/organization/OrganizationPage'
import QueuePage from '@/pages/queue/QueuePage'
import UsersAndPermissionsPage from '@/pages/users/UsersAndPermissionsPage'
import CompanySettingsPage from '@/pages/settings/CompanySettingsPage'

const App: React.FC = () => {
  const dispatch = useDispatch()
  const isAuthenticated = useSelector(selectIsAuthenticated)

  useEffect(() => {
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
        token: {
          colorPrimary: '#556b2f',
          borderRadius: 6,
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
            <Route path="/dashboard" element={<DashboardPage />} />
            
            {/* Organization */}
            <Route path="/organization" element={<OrganizationPage />} />
            
            {/* Queue */}
            <Route path="/queue" element={<QueuePage />} />
            
            {/* Users & Permissions */}
            <Route path="/users" element={<UsersAndPermissionsPage />} />
            
            {/* Settings */}
            <Route path="/settings" element={<CompanySettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App