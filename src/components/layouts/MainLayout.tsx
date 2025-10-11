import React, { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Layout, Avatar, Space, Badge, Typography, Button, Segmented, Tooltip } from 'antd'
import {
  ThunderboltOutlined,
  UserOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SmileOutlined,
  SafetyCertificateOutlined,
  PartitionOutlined,
  AppstoreOutlined,
  HistoryOutlined,
  ShoppingOutlined,
  HddOutlined,
} from '@/utils/optimizedIcons'
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
import { useTheme } from '@/context/ThemeContext'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'
import { RootState } from '@/store/store'
import { useCompanyInfo } from '@/api/queries/dashboard'
import { useQueryClient } from '@tanstack/react-query'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius } from '@/utils/styleConstants'
import SandboxWarning from '@/components/common/SandboxWarning'
import { useTelemetry } from '@/components/common/TelemetryProvider'
import { apiConnectionService } from '@/services/apiConnectionService'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' ? window.innerWidth < 768 : false)
  const [mobileMenuVisible, setMobileMenuVisible] = useState(false)
  const [isDevelopment, setIsDevelopment] = useState(false)
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
  const styles = useComponentStyles()
  const { trackUserAction } = useTelemetry()

  // Handle responsive behavior
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      if (mobile) {
        setCollapsed(true)
        setMobileMenuVisible(false)
      }
    }

    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

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

  // Check if we're in development environment
  useEffect(() => {
    const checkEnvironment = () => {
      const endpointInfo = apiConnectionService.getEndpointInfo()
      setIsDevelopment(endpointInfo?.type === 'localhost')
    }

    checkEnvironment()
  }, [])

  // Define all menu items with visibility flags
  const allMenuItems = [
    // Non-scrolling pages group
    {
      key: '/resources',
      icon: <AppstoreOutlined />,
      label: t('navigation.resources'),
      showInSimple: true,
      'data-testid': 'main-nav-resources',
    },
    {
      key: '/distributed-storage',
      icon: <HddOutlined />,
      label: t('navigation.distributedStorage'),
      showInSimple: false, // Show in expert mode only
      requiresPlan: ['ELITE', 'PREMIUM', 'Elite', 'Premium'], // Support both uppercase and proper case
      requiresDevelopment: true, // Only show in local development
      'data-testid': 'main-nav-distributed-storage',
    },
    {
      key: '/marketplace',
      icon: <ShoppingOutlined />,
      label: t('navigation.marketplace'),
      showInSimple: false,
      requiresDevelopment: true, // Only show in local development
      'data-testid': 'main-nav-marketplace',
    },
    {
      key: '/queue',
      icon: <ThunderboltOutlined />,
      label: t('navigation.queue'),
      showInSimple: false,
      'data-testid': 'main-nav-queue',
    },
    {
      key: '/audit',
      icon: <HistoryOutlined />,
      label: t('navigation.audit'),
      showInSimple: false,
      'data-testid': 'main-nav-audit',
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
      'data-testid': 'main-nav-architecture',
    },
    {
      key: '/system',
      icon: <SettingOutlined />,
      label: t('navigation.system'),
      showInSimple: true,
      'data-testid': 'main-nav-system',
    },
  ]

  // Handle mode transition
  const handleModeToggle = () => {
    setIsTransitioning(true)

    // Toggle the mode
    dispatch(toggleUiMode())

    // Determine the new mode
    const newMode = uiMode === 'simple' ? 'expert' : 'simple'

    // Track mode change
    trackUserAction('ui_mode_toggle', 'mode_switcher', {
      from_mode: uiMode,
      to_mode: newMode,
      current_page: location.pathname
    })
    
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
    
    // Clear transition state immediately
    setIsTransitioning(false)
  }

  const handleLogout = async () => {
    // Track logout action
    trackUserAction('logout', 'logout_button', {
      current_page: location.pathname,
      session_duration: Date.now() - (window as any).sessionStartTime || 0
    })

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
    .filter(item => {
      // Check UI mode visibility
      if (item.type !== 'divider' && !(uiMode === 'expert' || item.showInSimple)) {
        return false
      }

      // Check plan requirements
      if (item.requiresPlan) {
        // If no subscription data, hide the item
        if (!companyData?.activeSubscription) {
          return false
        }
        const currentPlan = companyData.activeSubscription.PlanName
        // Check if current plan matches any required plan (case-insensitive)
        const hasRequiredPlan = item.requiresPlan.some(
          requiredPlan => requiredPlan.toUpperCase() === currentPlan?.toUpperCase()
        )
        if (!hasRequiredPlan) {
          return false
        }
      }

      // Check development environment requirements
      if (item.requiresDevelopment && !isDevelopment) {
        return false
      }

      return true
    })
    .map(({ showInSimple, requiresPlan, requiresDevelopment, ...item }) => item)

  // Determine if current page needs no-scroll behavior
  const noScrollPages = ['/audit', '/resources', '/queue']
  const isNoScrollPage = noScrollPages.includes(location.pathname)

  return (
    <>
      <SandboxWarning />
      <Layout style={{ minHeight: '100vh' }} className={isNoScrollPage ? 'no-scroll-page' : ''}>
        {/* Mobile overlay */}
        {isMobile && mobileMenuVisible && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            zIndex: DESIGN_TOKENS.Z_INDEX.DROPDOWN - 2, // 998 - below navigation but above content
          }}
          onClick={() => setMobileMenuVisible(false)}
          aria-hidden="true"
          role="presentation"
        />
      )}
      <Sider
        trigger={null}
        collapsible
        collapsed={isMobile ? !mobileMenuVisible : collapsed}
        role="navigation"
        aria-label={t('navigation.mainNavigation')}
        style={{
          ...styles.sidebar,
          position: 'fixed',
          left: isMobile ? (mobileMenuVisible ? 0 : '-200px') : 0,
          top: 0,
          bottom: 0,
          height: '100vh',
          overflow: 'hidden',
          zIndex: DESIGN_TOKENS.Z_INDEX.DROPDOWN - 1, // 999 - below dropdowns and modals
          width: isMobile ? 200 : (collapsed ? 80 : 200),
          transition: `left ${DESIGN_TOKENS.TRANSITIONS.SLOW}, width ${DESIGN_TOKENS.TRANSITIONS.DEFAULT}`,
        }}
      >
        <div
          style={{
            height: DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT,
            ...styles.flexCenter,
            borderBottom: '1px solid var(--color-border-secondary)',
            padding: collapsed ? `0 ${spacing('SM')}px` : `0 ${spacing('MD')}px`,
            flexShrink: 0,
            cursor: 'pointer',
          }}
          onClick={() => {
            trackUserAction('navigation', '/dashboard', {
              trigger: 'logo_click',
              from_page: location.pathname
            })
            navigate('/dashboard')
          }}
          data-testid="main-logo-home"
        >
          <img
            src={theme === 'dark' ? logoWhite : logoBlack}
            alt="Rediacc Logo"
            style={{
              height: DESIGN_TOKENS.DIMENSIONS.ICON_XL,
              width: 'auto',
              maxWidth: collapsed ? 64 : 150,
              objectFit: 'contain',
              transition: `max-width ${DESIGN_TOKENS.TRANSITIONS.SLOW}`,
            }}
          />
        </div>
        <div style={{ ...styles.flexColumn as React.CSSProperties, height: `calc(100% - ${DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT}px)`, overflow: 'hidden' }}>
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            {menuItems.map((item) => {
              if (item.type === 'divider') {
                return <div key={item.key} style={{ height: 1, margin: '12px 16px', background: 'var(--color-border-secondary)', opacity: 0.6 }} />
              }
              
              const isSelected = location.pathname === item.key
              const menuItemContent = (
                <div
                  onClick={() => {
                    // Track navigation click
                    trackUserAction('navigation', item.key, {
                      menu_item: item.label,
                      ui_mode: uiMode,
                      is_mobile: isMobile,
                      sidebar_collapsed: collapsed,
                      from_page: location.pathname
                    })

                    navigate(item.key)
                    if (isMobile) {
                      setMobileMenuVisible(false)
                    }
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: collapsed ? '10px 0' : '10px 24px',
                    margin: '4px 8px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    minHeight: '44px',
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    backgroundColor: isSelected ? 'rgba(85, 107, 47, 0.1)' : 'transparent',
                    borderRight: isSelected ? '3px solid var(--color-primary)' : 'none',
                    color: isSelected ? 'var(--color-primary)' : 'var(--color-text-primary)',
                    fontWeight: isSelected ? 600 : 400,
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = 'var(--color-bg-hover)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = 'transparent'
                    }
                  }}
                  data-testid={item['data-testid']}
                >
                  <span style={{ 
                    fontSize: 20, 
                    marginRight: collapsed ? 0 : 12,
                    color: isSelected ? 'var(--color-primary)' : 'inherit',
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}>
                    {item.icon}
                  </span>
                  {!collapsed && <span>{item.label}</span>}
                </div>
              )

              if (collapsed) {
                return (
                  <Tooltip key={item.key} title={item.label} placement="right">
                    {menuItemContent}
                  </Tooltip>
                )
              }
              
              return <div key={item.key}>{menuItemContent}</div>
            })}
          </div>
          <div
            style={{
              borderTop: '1px solid var(--color-border-secondary)',
              background: 'var(--color-bg-secondary)',
            }}
          >
            {/* User info section */}
            <div
              style={{
                padding: collapsed ? `${spacing('SM')}px ${spacing('SM')}px` : `${spacing('SM')}px ${spacing('MD')}px`,
                borderBottom: '1px solid var(--color-border-secondary)',
                ...styles.flexStart,
                gap: spacing('SM'),
              }}
            >
              {collapsed ? (
                <Tooltip 
                  title={(
                    <div>
                      <div>{user?.email}</div>
                      {company && <div style={{ fontSize: '12px', marginTop: '4px' }}>{company}</div>}
                    </div>
                  )} 
                  placement="right"
                >
                  <Avatar 
                    icon={<UserOutlined />} 
                    size={DESIGN_TOKENS.DIMENSIONS.ICON_LG}
                    style={{ backgroundColor: 'var(--color-text-tertiary)', cursor: 'pointer' }} 
                  />
                </Tooltip>
              ) : (
                <>
                  <Avatar 
                    icon={<UserOutlined />} 
                    size={DESIGN_TOKENS.DIMENSIONS.ICON_XL}
                    style={{ backgroundColor: 'var(--color-text-tertiary)' }} 
                  />
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
                          color: 'var(--color-text-secondary)',
                        }}
                      >
                        {company}
                      </Text>
                    )}
                  </div>
                </>
              )}
            </div>
            
            {/* UI Mode switch section */}
            <div
              style={{
                padding: collapsed ? '16px 8px' : '16px',
                borderTop: '1px solid var(--color-border-secondary)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: collapsed ? 'center' : 'stretch',
                gap: 12,
                transition: 'all 0.3s ease',
              }}
            >
              {collapsed ? (
                <Tooltip 
                  title={uiMode === 'simple' ? t('uiMode.simple') : t('uiMode.expert')} 
                  placement="right"
                >
                  <div 
                    className="ui-mode-icon"
                    style={{ 
                      fontSize: 20, 
                      color: '#556b2f',
                      display: 'flex',
                      alignItems: 'center',
                      cursor: 'pointer',
                    }}
                    onClick={handleModeToggle}
                    data-testid="main-mode-icon"
                    aria-label={uiMode === 'simple' ? t('uiMode.simple') : t('uiMode.expert')}
                  >
                    {uiMode === 'simple' ? (
                      <SmileOutlined />
                    ) : (
                      <SafetyCertificateOutlined />
                    )}
                  </div>
                </Tooltip>
              ) : (
                <>
                  <Text style={{ 
                    fontSize: 12,
                    color: 'var(--color-text-secondary)',
                    textAlign: 'center',
                  }}>
                    {t('uiMode.label', { defaultValue: 'Interface Mode' })}
                  </Text>
                  <Segmented
                    block
                    value={uiMode}
                    onChange={(value) => {
                      if (value !== uiMode) {
                        handleModeToggle()
                      }
                    }}
                    options={[
                      {
                        label: (
                          <Space size={4} style={{ padding: '4px 0' }}>
                            <SmileOutlined />
                            <span>{t('uiMode.simple')}</span>
                          </Space>
                        ),
                        value: 'simple',
                      },
                      {
                        label: (
                          <Space size={4} style={{ padding: '4px 0' }}>
                            <SafetyCertificateOutlined />
                            <span>{t('uiMode.expert')}</span>
                          </Space>
                        ),
                        value: 'expert',
                      },
                    ]}
                    style={{
                      background: 'var(--color-bg-tertiary)',
                    }}
                    data-testid="main-mode-toggle"
                  />
                </>
              )}
            </div>
            
            {/* Logout button */}
            <div
              style={{
                padding: collapsed ? '8px' : '8px 16px',
                borderTop: '1px solid var(--color-border-secondary)',
              }}
            >
              {collapsed ? (
                <Tooltip title={t('navigation.logout')} placement="right">
                  <Button
                    type="text"
                    icon={<LogoutOutlined />}
                    onClick={handleLogout}
                    className="logout-button"
                    data-testid="main-logout-button"
                    aria-label={t('navigation.logout')}
                    style={{
                      width: '100%',
                      ...styles.flexStart,
                      justifyContent: 'center',
                      transition: DESIGN_TOKENS.TRANSITIONS.SLOW,
                      padding: `${spacing('XS')}px 0`,
                      minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                    }}
                  />
                </Tooltip>
              ) : (
                <Button
                  type="text"
                  icon={<LogoutOutlined />}
                  onClick={handleLogout}
                  className="logout-button"
                  data-testid="main-logout-button"
                  style={{
                    width: '100%',
                    ...styles.flexStart,
                    justifyContent: 'flex-start',
                    gap: spacing('SM'),
                    transition: DESIGN_TOKENS.TRANSITIONS.SLOW,
                    padding: `${spacing('XS')}px ${spacing('SM')}px`,
                    minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                  }}
                >
                  <span style={{ flex: 0 }}>{t('navigation.logout')}</span>
                </Button>
              )}
            </div>
          </div>
        </div>
      </Sider>
      <Layout style={{ 
        marginLeft: isMobile ? 0 : (collapsed ? 80 : 200), 
        transition: 'margin-left 0.2s' 
      }}>
        <Header
          style={{
            ...styles.header,
            padding: isMobile ? `0 ${spacing('MD')}px` : `0 ${spacing('CONTAINER')}px`,
            ...styles.flexBetween,
          }}
        >
          <Space>
            {isMobile ? (
              <Button
                type="text"
                icon={<MenuUnfoldOutlined />}
                onClick={() => {
                  trackUserAction('ui_interaction', 'mobile_menu_toggle', {
                    action: mobileMenuVisible ? 'close' : 'open',
                    current_page: location.pathname
                  })
                  setMobileMenuVisible(!mobileMenuVisible)
                }}
                data-testid="mobile-menu-toggle"
                aria-label={mobileMenuVisible ? t('navigation.closeMobileMenu') : t('navigation.openMobileMenu')}
                aria-expanded={mobileMenuVisible}
                style={{
                  ...styles.touchTarget,
                  fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_LG,
                }}
              />
            ) : collapsed ? (
              <Button
                type="text"
                icon={<MenuUnfoldOutlined />}
                onClick={() => {
                  trackUserAction('ui_interaction', 'sidebar_expand', {
                    current_page: location.pathname
                  })
                  setCollapsed(false)
                }}
                data-testid="main-sidebar-expand"
                style={{
                  ...styles.touchTarget,
                  fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_LG,
                }}
              />
            ) : (
              <Button
                type="text"
                icon={<MenuFoldOutlined />}
                onClick={() => {
                  trackUserAction('ui_interaction', 'sidebar_collapse', {
                    current_page: location.pathname
                  })
                  setCollapsed(true)
                }}
                data-testid="main-sidebar-collapse"
                style={{
                  ...styles.touchTarget,
                  fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_LG,
                }}
              />
            )}
            {company && !isMobile && (
              <Text strong style={{ marginLeft: spacing('MD') }}>
                {company}
              </Text>
            )}
            {companyData?.activeSubscription && !isMobile && (
              <Badge 
                count={companyData.activeSubscription.PlanName} 
                style={{ 
                  backgroundColor: 'var(--color-primary)',
                  fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
                  fontWeight: DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD,
                  padding: `0 ${spacing('SM') + 2}px`,
                  height: DESIGN_TOKENS.DIMENSIONS.ICON_LG,
                  lineHeight: `${DESIGN_TOKENS.DIMENSIONS.ICON_LG}px`,
                  borderRadius: borderRadius('XL'),
                  marginLeft: spacing('SM'),
                  boxShadow: DESIGN_TOKENS.SHADOWS.BUTTON_DEFAULT
                }}
              />
            )}
          </Space>
          <Space size={isMobile ? spacing('SM') : spacing('MD')} align="center">
            <LanguageSelector />
            <ThemeToggle />
            <NotificationBell />
          </Space>
        </Header>
        <Content
          style={{
            margin: isMobile ? spacing('XS') : spacing('SM'),
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
              <div style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XXXXL, color: 'var(--color-primary)', marginBottom: spacing('MD') }}>
                {uiMode === 'simple' ? <SafetyCertificateOutlined /> : <SmileOutlined />}
              </div>
              <Text style={{ fontSize: 18, color: 'var(--color-text-secondary)' }}>
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
    </>
  )
}

export default MainLayout