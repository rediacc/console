import React, { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Layout, Menu, Avatar, Dropdown, Space, Badge, Typography, Switch, Button } from 'antd'
import {
  DashboardOutlined,
  TeamOutlined,
  GlobalOutlined,
  ApiOutlined,
  CloudServerOutlined,
  FolderOutlined,
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
  PartitionOutlined,
  EnvironmentOutlined,
  AppstoreOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { selectUser, selectCompany } from '@/store/auth/authSelectors'
import { logout, updateCompany } from '@/store/auth/authSlice'
import { masterPasswordService } from '@/services/masterPasswordService'
import { toggleUiMode } from '@/store/ui/uiSlice'
import { clearAuthData, saveAuthData, getAuthData } from '@/utils/auth'
import apiClient from '@/api/client'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import LanguageSelector from '@/components/common/LanguageSelector'
import NotificationBell from '@/components/common/NotificationBell'
import QueueManagerStatus from '@/components/common/QueueManagerStatus'
import { useTheme } from '@/context/ThemeContext'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'
import { RootState } from '@/store/store'
import { useCompanyInfo } from '@/api/queries/dashboard'
import { useQueryClient } from '@tanstack/react-query'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useDispatch()
  const queryClient = useQueryClient()
  const user = useSelector(selectUser)
  const company = useSelector(selectCompany)
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const { theme } = useTheme()
  const { t } = useTranslation('common')
  const { data: companyData } = useCompanyInfo()

  // Update company name when company data is loaded
  useEffect(() => {
    const updateCompanyData = async () => {
      if (companyData?.companyInfo?.CompanyName && companyData.companyInfo.CompanyName !== company) {
        dispatch(updateCompany(companyData.companyInfo.CompanyName))
        // Also update secure storage to persist the company name
        const authData = await getAuthData()
        if (authData.token && authData.email) {
          await saveAuthData(authData.token, authData.email, companyData.companyInfo.CompanyName)
        }
      }
    }
    
    updateCompanyData()
  }, [companyData, company, dispatch])

  // Define all menu items with visibility flags
  const allMenuItems = [
    // Non-scrolling pages group
    {
      key: '/resources',
      icon: <AppstoreOutlined />,
      label: t('navigation.resources'),
      showInSimple: true,
    },
    {
      key: '/queue',
      icon: <ThunderboltOutlined />,
      label: t('navigation.queue'),
      showInSimple: false,
    },
    {
      key: '/audit',
      icon: <HistoryOutlined />,
      label: t('navigation.audit'),
      showInSimple: false,
    },
    {
      key: 'divider-1',
      type: 'divider',
      showInSimple: true,
    },
    // Scrolling pages group
    {
      key: '/architecture',
      icon: <PartitionOutlined />,
      label: t('navigation.architecture'),
      showInSimple: false,
    },
    {
      key: '/system',
      icon: <SettingOutlined />,
      label: t('navigation.system'),
      showInSimple: true,
    },
  ]

  // Handle mode transition
  const handleModeToggle = () => {
    setIsTransitioning(true)
    
    // Toggle the mode
    dispatch(toggleUiMode())
    
    // Determine the new mode
    const newMode = uiMode === 'simple' ? 'expert' : 'simple'
    
    // Check if current page is visible in the new mode
    const currentPath = location.pathname
    const currentMenuItem = allMenuItems.find(item => item.key === currentPath)
    
    const isCurrentPageVisibleInNewMode = currentMenuItem && (
      newMode === 'expert' || currentMenuItem.showInSimple
    )
    
    // Only navigate if current page is not visible in new mode
    if (!isCurrentPageVisibleInNewMode) {
      const firstVisibleItem = allMenuItems.find(item => 
        item.type !== 'divider' && (newMode === 'expert' || item.showInSimple)
      )
      
      if (firstVisibleItem) {
        navigate(firstVisibleItem.key)
      }
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
    masterPasswordService.clearMasterPassword() // Clear master password from secure memory
    queryClient.clear() // Clear all React Query caches
    dispatch(logout())
    navigate('/login')
  }

  const menuItems = allMenuItems
    .filter(item => item.type === 'divider' || uiMode === 'expert' || item.showInSimple)
    .map(({ showInSimple, ...item }) => item)

  // Don't select any menu during transition
  const selectedKeys = isTransitioning ? [] : [location.pathname]
  const openKeys = menuItems
    .filter(item => item.children?.some(child => child.key === location.pathname))
    .map(item => item.key)

  // Determine if current page needs no-scroll behavior
  const noScrollPages = ['/audit', '/resources', '/queue']
  const isNoScrollPage = noScrollPages.includes(location.pathname)

  return (
    <Layout style={{ minHeight: '100vh' }} className={isNoScrollPage ? 'no-scroll-page' : ''}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        style={{
          background: theme === 'dark' ? '#1a1a1a' : '#fff',
          boxShadow: theme === 'dark' ? '2px 0 8px rgba(0,0,0,0.3)' : '2px 0 8px rgba(0,0,0,0.06)',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          height: '100vh',
          overflow: 'hidden',
          zIndex: 100,
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
            flexShrink: 0,
            cursor: 'pointer',
          }}
          onClick={() => navigate('/dashboard')}
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
        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 64px)', overflow: 'hidden' }}>
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
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
                borderRight: 0,
                transition: 'all 0.3s ease',
              }}
            />
          </div>
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
                style={{ backgroundColor: '#666666' }} 
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
                className="logout-button"
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  gap: collapsed ? 0 : 8,
                  transition: 'all 0.3s ease',
                  padding: collapsed ? '4px 0' : '4px 12px',
                }}
              >
                {!collapsed && (
                  <span style={{ flex: 0 }}>{t('navigation.logout')}</span>
                )}
              </Button>
            </div>
          </div>
        </div>
      </Sider>
      <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s' }}>
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
            {companyData?.activeSubscription && (
              <Badge 
                count={companyData.activeSubscription.PlanName} 
                style={{ 
                  backgroundColor: '#556b2f',
                  fontSize: '12px',
                  padding: '0 8px',
                  height: '22px',
                  lineHeight: '22px',
                  borderRadius: '11px',
                  marginLeft: 8
                }}
              />
            )}
          </Space>
          <Space size={16} align="center">
            {uiMode === 'expert' && <QueueManagerStatus />}
            <LanguageSelector />
            <ThemeToggle />
            <NotificationBell />
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