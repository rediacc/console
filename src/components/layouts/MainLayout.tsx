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
import { selectUser, selectCompany } from '@/store/auth/authSelectors'
import { logout } from '@/store/auth/authSlice'
import { clearAuthData } from '@/utils/auth'
import apiClient from '@/api/client'
import MessageHistory from '@/components/common/MessageHistory'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useDispatch()
  const user = useSelector(selectUser)
  const company = useSelector(selectCompany)

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
        label: 'Settings',
        onClick: () => navigate('/settings'),
      },
      {
        type: 'divider',
      },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: 'Logout',
        onClick: handleLogout,
      },
    ],
  }

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: 'Dashboard',
    },
    {
      key: 'resources',
      icon: <DatabaseOutlined />,
      label: 'Resources',
      children: [
        {
          key: '/teams',
          icon: <TeamOutlined />,
          label: 'Teams',
        },
        {
          key: '/regions',
          icon: <GlobalOutlined />,
          label: 'Regions',
        },
        {
          key: '/bridges',
          icon: <ApiOutlined />,
          label: 'Bridges',
        },
        {
          key: '/machines',
          icon: <CloudServerOutlined />,
          label: 'Machines',
        },
        {
          key: '/repositories',
          icon: <DatabaseOutlined />,
          label: 'Repositories',
        },
        {
          key: '/storages',
          icon: <HddOutlined />,
          label: 'Storage',
        },
        {
          key: '/schedules',
          icon: <ScheduleOutlined />,
          label: 'Schedules',
        },
      ],
    },
    {
      key: '/queue',
      icon: <ThunderboltOutlined />,
      label: 'Queue Management',
    },
    {
      key: 'users',
      icon: <UserOutlined />,
      label: 'Users & Permissions',
      children: [
        {
          key: '/users',
          icon: <UserOutlined />,
          label: 'Users',
        },
        {
          key: '/permissions',
          icon: <SafetyOutlined />,
          label: 'Permissions',
        },
      ],
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: 'Company Settings',
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
          background: '#fff',
          boxShadow: '2px 0 8px rgba(0,0,0,0.06)',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Text strong style={{ fontSize: collapsed ? 20 : 24, color: '#556b2f' }}>
            {collapsed ? 'R' : 'Rediacc'}
          </Text>
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
            background: '#fff',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
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