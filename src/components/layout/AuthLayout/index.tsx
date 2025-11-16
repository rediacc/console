import React from 'react'
import { Outlet } from 'react-router-dom'
import { Space } from 'antd'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import LanguageSelector from '@/components/common/LanguageSelector'
import { AuthLayoutContainer, ControlsWrapper, AuthContent } from './styles'

const AuthLayout: React.FC = () => {
  return (
    <AuthLayoutContainer data-testid="auth-layout-container">
      <ControlsWrapper data-testid="auth-layout-controls-wrapper">
        <Space size="small">
          <LanguageSelector iconOnly={true} />
          <ThemeToggle data-testid="auth-layout-theme-toggle" />
        </Space>
      </ControlsWrapper>
      <AuthContent data-testid="auth-layout-content">
        <Outlet />
      </AuthContent>
    </AuthLayoutContainer>
  )
}

export default AuthLayout
