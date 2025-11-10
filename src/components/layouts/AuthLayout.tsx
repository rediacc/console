import React from 'react'
import { Outlet } from 'react-router-dom'
import { Layout, Space } from 'antd'
import { useTheme } from '@/context/ThemeContext'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import LanguageSelector from '@/components/common/LanguageSelector'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing } from '@/utils/styleConstants'

const { Content } = Layout

const AuthLayout: React.FC = () => {
  const { theme } = useTheme()
  const styles = useComponentStyles()

  const backgroundStyle = theme === 'dark'
    ? { background: '#0a0a0a' }
    : { background: '#f8f9fa' }

  return (
    <Layout style={{ minHeight: '100vh', ...backgroundStyle }} data-testid="auth-layout-container">
      <div
        style={{
          position: 'absolute',
          top: spacing('PAGE_CONTAINER'),
          right: spacing('PAGE_CONTAINER'),
          zIndex: DESIGN_TOKENS.Z_INDEX.DROPDOWN
        }}
        className="auth-controls-wrapper"
        data-testid="auth-layout-controls-wrapper"
      >
        <Space size="small">
          <LanguageSelector iconOnly={true} />
          <ThemeToggle data-testid="auth-layout-theme-toggle" />
        </Space>
      </div>
      <Content
        style={{
          ...styles.flexCenter,
          padding: spacing('PAGE_CONTAINER'),
        }}
        data-testid="auth-layout-content"
        className="auth-layout-content"
      >
        <Outlet />
      </Content>
    </Layout>
  )
}

export default AuthLayout
