import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Layout, Menu, Avatar, Dropdown, Space, Badge, Typography } from 'antd'
import {
  DashboardOutlined,
  TeamOutlined,
  GlobalOutlined,
  ApiOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  HddOutlined,
  ScheduleOutlined,
  ThunderboltOutlined,
  UserOutlined,
  SafetyOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { selectUser, selectCompany } from '@/store/auth/authSelectors'
import { logout } from '@/store/auth/authSlice'
import { clearAuthData } from '@/utils/auth'
import apiClient from '@/api/client'
import MessageHistory from '@/components/common/MessageHistory'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import LanguageSelector from '@/components/common/LanguageSelector'
import { useTheme } from '@/context/ThemeContext'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useDispatch()
  const user = useSelector(selectUser)
  const company = useSelector(selectCompany)
  const { theme } = useTheme()
  const { t } = useTranslation('common')

  const handleLogout = async () => {
    try {
      await apiClient.logout()
    } catch (error) {
      // Continue with logout even if API call fails
    }
    clearAuthData()
    dispatch(logout())
    navigate('/login')
  }

  const userMenu = {
    items: [
      {
        key: 'profile',
        icon: <UserOutlined />,
        label: 'Profile',
        onClick: () => navigate('/profile'),
      },
      {
        key: 'settings',
        icon: <SettingOutlined />,
        label: t('navigation.settings'),
        onClick: () => navigate('/settings'),
      },
      {
        type: 'divider',
      },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: t('navigation.logout'),
        onClick: handleLogout,
      },
    ],
  }

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: t('navigation.dashboard'),
    },
    {
      key: '/organization',
      icon: <TeamOutlined />,
      label: t('navigation.organization'),
    },
    {
      key: '/queue',
      icon: <ThunderboltOutlined />,
      label: t('navigation.queue'),
    },
    {
      key: '/users',
      icon: <UserOutlined />,
      label: t('navigation.users'),
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: t('navigation.settings'),
    },
  ]

  const selectedKeys = [location.pathname]
  const openKeys = menuItems
    .filter(item => item.children?.some(child => child.key === location.pathname))
    .map(item => item.key)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        style={{
          background: theme === 'dark' ? '#1a1a1a' : '#fff',
          boxShadow: theme === 'dark' ? '2px 0 8px rgba(0,0,0,0.3)' : '2px 0 8px rgba(0,0,0,0.06)',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid #f0f0f0',
            padding: '0 16px',
          }}
        >
          <img
            src={theme === 'dark' ? logoWhite : logoBlack}
            alt="Rediacc Logo"
            style={{
              height: 32,
              width: 'auto',
              maxWidth: 150,
              objectFit: 'contain',
            }}
          />
        </div>
        <Menu
          mode="inline"
          selectedKeys={selectedKeys}
          defaultOpenKeys={openKeys}
          items={menuItems}
          onClick={({ key }) => {
            if (key.startsWith('/')) {
              navigate(key)
            }
          }}
          style={{ height: 'calc(100% - 64px)', borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: '0 24px',
            background: theme === 'dark' ? '#1a1a1a' : '#fff',
            boxShadow: theme === 'dark' ? '0 2px 8px rgba(0,0,0,0.3)' : '0 2px 8px rgba(0,0,0,0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Space>
            {collapsed ? (
              <MenuUnfoldOutlined
                style={{ fontSize: 18, cursor: 'pointer' }}
                onClick={() => setCollapsed(false)}
              />
            ) : (
              <MenuFoldOutlined
                style={{ fontSize: 18, cursor: 'pointer' }}
                onClick={() => setCollapsed(true)}
              />
            )}
            {company && (
              <Text strong style={{ marginLeft: 16 }}>
                {company}
              </Text>
            )}
          </Space>
          <Space size={16}>
            <LanguageSelector />
            <ThemeToggle />
            <MessageHistory />
            <Dropdown menu={userMenu} placement="bottomRight" arrow>
              <Space style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#556b2f' }} />
                <Text>{user?.email}</Text>
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content
          style={{
            margin: '24px',
            minHeight: 280,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout