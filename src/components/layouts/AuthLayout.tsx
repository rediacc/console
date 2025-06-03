import React from 'react'
import { Outlet } from 'react-router-dom'
import { Layout } from 'antd'
import { useTheme } from '@/context/ThemeContext'
import { ThemeToggle } from '@/components/common/ThemeToggle'

const { Content } = Layout

const AuthLayout: React.FC = () => {
  const { theme } = useTheme()
  
  const backgroundStyle = theme === 'dark' 
    ? { background: 'linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%)' }
    : { background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)' }
  
  return (
    <Layout style={{ minHeight: '100vh', ...backgroundStyle }}>
      <div style={{ 
        position: 'absolute', 
        top: 20, 
        right: 20, 
        zIndex: 1000 
      }}>
        <ThemeToggle />
      </div>
      <Content
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '24px',
        }}
      >
        <Outlet />
      </Content>
    </Layout>
  )
}

export default AuthLayout