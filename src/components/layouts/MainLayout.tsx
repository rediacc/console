import React, { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Layout, Menu, Avatar, Dropdown, Space, Badge, Typography, Switch, Button } from 'antd'
import {
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
  ExperimentOutlined,
  SmileOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { selectUser, selectCompany } from '@/store/auth/authSelectors'
import { logout } from '@/store/auth/authSlice'
import { toggleUiMode } from '@/store/ui/uiSlice'
import { clearAuthData } from '@/utils/auth'
import apiClient from '@/api/client'
import MessageHistory from '@/components/common/MessageHistory'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import LanguageSelector from '@/components/common/LanguageSelector'
import { useTheme } from '@/context/ThemeContext'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'
import { RootState } from '@/store/store'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useDispatch()
  const user = useSelector(selectUser)
  const company = useSelector(selectCompany)
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const { theme } = useTheme()
  const { t } = useTranslation('common')

  // Define all menu items with visibility flags
  const allMenuItems = [
    {
      key: '/organization',
      icon: <TeamOutlined />,
      label: t('navigation.organization'),
      showInSimple: true,
    },
    {
      key: '/users',
      icon: <UserOutlined />,
      label: t('navigation.users'),
      showInSimple: true,
    },
    {
      key: '/machines',
      icon: <CloudServerOutlined />,
      label: t('navigation.machines'),
      showInSimple: true,
    },
    {
      key: '/queue',
      icon: <ThunderboltOutlined />,
      label: t('navigation.queue'),
      showInSimple: false,
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: t('navigation.settings'),
      showInSimple: true,
    },
  ]

  // Handle mode transition
  const handleModeToggle = () => {
    setIsTransitioning(true)
    
    // Toggle the mode
    dispatch(toggleUiMode())
    
    // Determine the first visible menu item for the new mode
    const newMode = uiMode === 'simple' ? 'expert' : 'simple'
    const firstVisibleItem = allMenuItems.find(item => 
      newMode === 'expert' || item.showInSimple
    )
    
    // Navigate to the first visible menu item
    if (firstVisibleItem) {
      navigate(firstVisibleItem.key)
    }
    
    // Clear transition state after animation
    setTimeout(() => {
      setIsTransitioning(false)
    }, 600)
  }

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

  const menuItems = allMenuItems
    .filter(item => uiMode === 'expert' || item.showInSimple)
    .map(({ showInSimple, ...item }) => item)

  // Don't select any menu during transition
  const selectedKeys = isTransitioning ? [] : [location.pathname]
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
            padding: collapsed ? '0 8px' : '0 16px',
          }}
        >
          <img
            src={theme === 'dark' ? logoWhite : logoBlack}
            alt="Rediacc Logo"
            style={{
              height: 32,
              width: 'auto',
              maxWidth: collapsed ? 64 : 150,
              objectFit: 'contain',
              transition: 'max-width 0.3s ease',
            }}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 64px)' }}>
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
            style={{ 
              flex: 1, 
              borderRight: 0,
              transition: 'all 0.3s ease',
            }}
          />
          <div
            style={{
              borderTop: '1px solid #f0f0f0',
              background: theme === 'dark' ? '#1a1a1a' : '#fff',
            }}
          >
            {/* User info section */}
            <div
              style={{
                padding: collapsed ? '12px 8px' : '12px 16px',
                borderBottom: '1px solid #f0f0f0',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <Avatar 
                icon={<UserOutlined />} 
                size={collapsed ? 24 : 32}
                style={{ backgroundColor: '#556b2f' }} 
              />
              {!collapsed && (
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <Text 
                    ellipsis 
                    style={{ 
                      display: 'block', 
                      fontSize: '14px',
                      fontWeight: 500,
                    }}
                  >
                    {user?.email}
                  </Text>
                  {company && (
                    <Text 
                      ellipsis
                      style={{ 
                        display: 'block', 
                        fontSize: '12px',
                        color: '#666',
                      }}
                    >
                      {company}
                    </Text>
                  )}
                </div>
              )}
            </div>
            
            {/* UI Mode switch section */}
            <div
              style={{
                padding: collapsed ? '16px 8px' : '16px',
                borderTop: '1px solid #f0f0f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: collapsed ? 'center' : 'space-between',
                gap: 8,
                transition: 'all 0.3s ease',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  flex: collapsed ? 0 : 1,
                  transition: 'all 0.3s ease',
                }}
              >
                <div 
                  className="ui-mode-icon"
                  style={{ 
                    fontSize: 20, 
                    color: '#556b2f',
                    display: 'flex',
                    alignItems: 'center',
                    cursor: collapsed ? 'pointer' : 'default',
                  }}
                  onClick={collapsed ? handleModeToggle : undefined}
                >
                  {uiMode === 'simple' ? (
                    <SmileOutlined />
                  ) : (
                    <SafetyCertificateOutlined />
                  )}
                </div>
                {!collapsed && (
                  <Text style={{ 
                    opacity: 1,
                    transition: 'opacity 0.3s ease',
                  }}>
                    {uiMode === 'simple' ? t('uiMode.simple') : t('uiMode.expert')}
                  </Text>
                )}
              </div>
              {!collapsed && (
                <Switch
                  size="small"
                  checked={uiMode === 'expert'}
                  onChange={handleModeToggle}
                />
              )}
            </div>
            
            {/* Logout button */}
            <div
              style={{
                padding: collapsed ? '8px' : '8px 16px',
                borderTop: '1px solid #f0f0f0',
              }}
            >
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={handleLogout}
                style={{
                  width: '100%',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  color: '#666',
                  transition: 'all 0.3s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = '#556b2f';
                  e.currentTarget.style.backgroundColor = 'rgba(85, 107, 47, 0.08)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = '#666';
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                {!collapsed && t('navigation.logout')}
              </Button>
            </div>
          </div>
        </div>
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
          <Space size={16} align="center">
            <LanguageSelector />
            <ThemeToggle />
            <MessageHistory />
          </Space>
        </Header>
        <Content
          style={{
            margin: '24px',
            minHeight: 280,
            position: 'relative',
          }}
        >
          {isTransitioning ? (
            <div
              className="mode-transition"
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 48, color: '#556b2f', marginBottom: 16 }}>
                {uiMode === 'simple' ? <SafetyCertificateOutlined /> : <SmileOutlined />}
              </div>
              <Text style={{ fontSize: 18, color: '#666' }}>
                {t('uiMode.switching', { mode: uiMode === 'simple' ? t('uiMode.expert') : t('uiMode.simple') })}
              </Text>
            </div>
          ) : (
            <div style={{ animation: 'fadeIn 0.3s ease-in' }}>
              <Outlet />
            </div>
          )}
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout