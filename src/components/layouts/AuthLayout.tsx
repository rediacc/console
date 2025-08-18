import React from 'react'
import { Outlet } from 'react-router-dom'
import { Layout } from 'antd'
import { useTheme } from '@/context/ThemeContext'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing } from '@/utils/styleConstants'

const { Content } = Layout

const AuthLayout: React.FC = () => {
  const { theme } = useTheme()
  const styles = useComponentStyles()
  
  const backgroundStyle = theme === 'dark' 
    ? { background: 'linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%)' }
    : { background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)' }
  
  return (
    <Layout style={{ minHeight: '100vh', ...backgroundStyle }} data-testid="auth-layout-container">
      <div style={{ 
        position: 'absolute', 
        top: spacing('CONTAINER'), 
        right: spacing('CONTAINER'), 
        zIndex: DESIGN_TOKENS.Z_INDEX.DROPDOWN 
      }} data-testid="auth-layout-theme-toggle-wrapper">
        <ThemeToggle data-testid="auth-layout-theme-toggle" />
      </div>
      <Content
        style={{
          ...styles.flexCenter,
          padding: spacing('CONTAINER'),
        }}
        data-testid="auth-layout-content"
      >
        <Outlet />
      </Content>
    </Layout>
  )
}

export default AuthLayout