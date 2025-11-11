import React, { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Layout, Avatar, Space, Badge, Typography, Button, Segmented, Dropdown, Divider, Tooltip, message } from 'antd'
import {
  ThunderboltOutlined,
  UserOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuOutlined,
  SmileOutlined,
  SafetyCertificateOutlined,
  PartitionOutlined,
  DesktopOutlined,
  HistoryOutlined,
  ShoppingOutlined,
  HddOutlined,
  InboxOutlined,
  CloudOutlined,
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
import { featureFlags } from '@/config/featureFlags'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const SIDEBAR_EXPANDED_WIDTH = 200
const SIDEBAR_COLLAPSED_WIDTH = 64
const HEADER_ACTION_SIZE = 48
const HEADER_HEIGHT = DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT

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
  const styles = useComponentStyles()
  const { trackUserAction } = useTelemetry()

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

  // Keyboard shortcut handler for global power mode (Ctrl+Shift+E)
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'E') {
        e.preventDefault()

        // Check if running on localhost
        const onLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

        // Toggle global power mode (or localhost mode if on localhost)
        const newState = featureFlags.togglePowerMode()

        // Show toast with current state - different message for localhost vs non-localhost
        const msg = onLocalhost
          ? (newState ? 'Localhost Mode - All features enabled' : 'Localhost Mode - All features disabled')
          : (newState ? 'Advanced options enabled' : 'Advanced options disabled')

        message.info(msg)

        // Console log for debugging
        console.log(`[${onLocalhost ? 'LocalhostMode' : 'PowerMode'}] ${msg}`)
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [])

  // Define all menu items with visibility flags
  const allMenuItems = [
    // Non-scrolling pages group
    {
      key: '/machines',
      icon: <DesktopOutlined />,
      label: t('navigation.machines'),
      showInSimple: true,
      'data-testid': 'main-nav-machines',
    },
    {
      key: '/credentials',
      icon: <InboxOutlined />,
      label: t('navigation.credentials'),
      showInSimple: false,
      'data-testid': 'main-nav-credentials',
    },
    {
      key: '/storage',
      icon: <CloudOutlined />,
      label: t('navigation.storage'),
      showInSimple: false,
      'data-testid': 'main-nav-storage',
    },
    {
      key: '/distributed-storage',
      icon: <HddOutlined />,
      label: t('navigation.distributedStorage'),
      showInSimple: false, // Show in expert mode only
      requiresPlan: ['ENTERPRISE', 'BUSINESS', 'Enterprise', 'Business'], // Support both uppercase and proper case
      featureFlag: 'distributedStorage', // Beta feature - managed by feature flags
      'data-testid': 'main-nav-distributed-storage',
    },
    {
      key: '/marketplace',
      icon: <ShoppingOutlined />,
      label: t('navigation.marketplace'),
      showInSimple: false,
      featureFlag: 'marketplace', // Beta feature - managed by feature flags
      'data-testid': 'main-nav-marketplace',
    },
    {
      key: '/queue',
      icon: <ThunderboltOutlined />,
      label: t('navigation.queue'),
      showInSimple: false,
      featureFlag: 'queueManagement', // Expert mode feature - managed by feature flags
      'data-testid': 'main-nav-queue',
    },
    {
      key: '/audit',
      icon: <HistoryOutlined />,
      label: t('navigation.audit'),
      showInSimple: false,
      featureFlag: 'auditLogs', // Expert mode feature - managed by feature flags
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
      featureFlag: 'architecture', // Beta feature - managed by feature flags
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

  const handleSidebarToggle = () => {
    const action = collapsed ? 'sidebar_expand' : 'sidebar_collapse'
    trackUserAction('ui_interaction', action, {
      current_page: location.pathname
    })
    setCollapsed(prev => !prev)
  }

  // Filter and map menu items based on UI mode, plan, and feature flags
  // React Compiler will automatically optimize this
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
        const currentPlan = companyData.activeSubscription.PlanCode
        // Check if current plan matches any required plan (already uppercase)
        const hasRequiredPlan = item.requiresPlan.some(
          requiredPlan => requiredPlan.toUpperCase() === currentPlan
        )
        if (!hasRequiredPlan) {
          return false
        }
      }

      // Check feature flag requirements (replaces requiresDevelopment)
      if (item.featureFlag && !featureFlags.isEnabled(item.featureFlag)) {
        return false
      }

      return true
    })
    .map(({ showInSimple, requiresPlan, featureFlag, ...item }) => item)

  // Determine if current page needs no-scroll behavior
  // All pages are now scrollable, so no pages need the no-scroll class
  const noScrollPages: string[] = []
  const isNoScrollPage = noScrollPages.includes(location.pathname)
  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH
  const contentMargin = 0

  const userMenuOverlay = (
    <div
      style={{
        width: 320,
        backgroundColor: 'var(--color-bg-primary)',
        borderRadius: borderRadius('LG'),
        boxShadow: DESIGN_TOKENS.SHADOWS.XL,
        border: '1px solid var(--color-border-secondary)',
        padding: spacing('MD'),
        display: 'flex',
        flexDirection: 'column',
        gap: spacing('MD'),
      }}
    >
      <div style={{ display: 'flex', gap: spacing('SM'), alignItems: 'center' }}>
        <Avatar
          icon={<UserOutlined />}
          size={DESIGN_TOKENS.DIMENSIONS.ICON_XXL}
          style={{ backgroundColor: 'var(--color-text-tertiary)' }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <Text strong style={{ display: 'block' }}>
            {user?.email}
          </Text>
          {company && (
            <Text style={{ fontSize: 12, color: 'var(--color-text-secondary)', display: 'block' }}>
              {company}
            </Text>
          )}
          {companyData?.activeSubscription && (
            <Badge
              count={companyData.activeSubscription.PlanCode}
              style={{
                backgroundColor: 'var(--color-primary)',
                fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
                fontWeight: DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD,
                padding: `0 ${spacing('SM')}px`,
                height: DESIGN_TOKENS.DIMENSIONS.ICON_MD,
                lineHeight: `${DESIGN_TOKENS.DIMENSIONS.ICON_MD}px`,
                borderRadius: borderRadius('XL'),
                marginTop: spacing('XS'),
                boxShadow: DESIGN_TOKENS.SHADOWS.BUTTON_DEFAULT,
              }}
            />
          )}
        </div>
      </div>

      <Divider style={{ margin: 0 }} />

      <div>
        <Text
          style={{
            fontSize: 12,
            color: 'var(--color-text-secondary)',
          }}
        >
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
                <Space size={4}>
                  <SmileOutlined />
                  <span>{t('uiMode.simple')}</span>
                </Space>
              ),
              value: 'simple',
            },
            {
              label: (
                <Space size={4}>
                  <SafetyCertificateOutlined />
                  <span>{t('uiMode.expert')}</span>
                </Space>
              ),
              value: 'expert',
            },
          ]}
          style={{ marginTop: spacing('XS'), background: 'var(--color-bg-tertiary)' }}
          data-testid="main-mode-toggle"
        />
      </div>

      <Divider style={{ margin: 0 }} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: spacing('SM') }}>
        <div>
          <Text strong style={{ display: 'block' }}>
            {t('appearance.label', { defaultValue: 'Appearance' })}
          </Text>
          <Text style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
            {t('appearance.description', { defaultValue: 'Device theme' })}
          </Text>
        </div>
        <ThemeToggle />
      </div>

      <Divider style={{ margin: 0 }} />

      <div>
        <Text strong style={{ display: 'block', marginBottom: spacing('XS') }}>
          {t('language.label', { defaultValue: 'Language' })}
        </Text>
        <LanguageSelector iconOnly={false} />
      </div>

      <Divider style={{ margin: 0 }} />

      <Button
        type="text"
        icon={<LogoutOutlined />}
        onClick={handleLogout}
        className="logout-button"
        data-testid="main-logout-button"
        style={{ width: '100%', justifyContent: 'flex-start', gap: spacing('SM') }}
      >
        {t('navigation.logout')}
      </Button>
    </div>
  )

  return (
    <>
      <SandboxWarning />
      <Layout style={{ minHeight: '100vh' }} className={isNoScrollPage ? 'no-scroll-page' : ''}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={SIDEBAR_EXPANDED_WIDTH}
        collapsedWidth={SIDEBAR_COLLAPSED_WIDTH}
        role="navigation"
        aria-label={t('navigation.mainNavigation')}
        style={{
          ...styles.sidebar,
          position: 'fixed',
          left: 0,
          top: DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT,
          height: `calc(100vh - ${DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT}px)`,
          overflow: 'hidden',
          zIndex: DESIGN_TOKENS.Z_INDEX.DROPDOWN - 1, // 999 - below dropdowns and modals
          width: sidebarWidth,
          borderRight: 'none',
          boxShadow: 'none',
          transition: `left ${DESIGN_TOKENS.TRANSITIONS.SLOW}, width ${DESIGN_TOKENS.TRANSITIONS.DEFAULT}`,
        }}
      >
        <div
          style={{
            ...styles.flexColumn as React.CSSProperties,
            height: '100%',
            overflow: 'hidden',
            paddingTop: spacing('MD'),
          }}
        >
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', paddingBottom: spacing('LG') }}>
            {menuItems.map((item) => {
              if (item.type === 'divider') {
                return <React.Fragment key={item.key} />
              }
              
              const isSelected = location.pathname === item.key
              const padding = collapsed ? '10px 12px' : '10px 18px'
              const itemKey = item.key || item.label
              const menuItemContent = (
                <div
                  key={itemKey}
                  onClick={() => {
                    // Track navigation click
                    trackUserAction('navigation', item.key, {
                      menu_item: item.label,
                      ui_mode: uiMode,
                      sidebar_collapsed: collapsed,
                      from_page: location.pathname
                    })

                    navigate(item.key)
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding,
                    margin: '4px 12px',
                    borderRadius: '12px',
                    cursor: 'pointer',
                    minHeight: 44,
                    justifyContent: 'flex-start',
                    backgroundColor: isSelected ? 'var(--color-primary-bg)' : 'transparent',
                    color: isSelected ? 'var(--color-primary)' : 'var(--color-text-primary)',
                    fontWeight: isSelected ? 600 : 500,
                    transition: 'background-color 0.2s ease, color 0.2s ease',
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
                    marginRight: 12,
                    color: isSelected ? 'var(--color-primary)' : 'inherit',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 20,
                    height: 20,
                    flexShrink: 0,
                  }}>
                    {item.icon}
                  </span>
                  <span
                    style={{
                      marginLeft: 8,
                      overflow: 'hidden',
                      whiteSpace: 'nowrap',
                      textOverflow: 'ellipsis',
                      color: isSelected ? 'var(--color-primary)' : 'var(--color-text-primary)',
                      opacity: collapsed ? 0.85 : 1,
                      transition: 'opacity 0.2s ease',
                      flex: 1,
                    }}
                  >
                    {item.label}
                  </span>
                </div>
              )

              if (collapsed) {
                return (
                  <Tooltip key={itemKey} title={item.label} placement="right">
                    {menuItemContent}
                  </Tooltip>
                )
              }

              return menuItemContent
            })}
          </div>
        </div>
      </Sider>
      <Layout>
        <Header
          style={{
            ...styles.header,
            paddingRight: spacing('PAGE_CONTAINER'),
            paddingLeft: spacing('MD'),
            ...styles.flexBetween,
            boxShadow: theme === 'dark' ? DESIGN_TOKENS.SHADOWS.HEADER_DARK : DESIGN_TOKENS.SHADOWS.HEADER,
            borderBottom: '1px solid var(--color-border-secondary)',
            backgroundColor: 'var(--color-bg-primary)',
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            height: HEADER_HEIGHT,
            width: '100%',
            zIndex: DESIGN_TOKENS.Z_INDEX.DROPDOWN + 1,
            transition: `${DESIGN_TOKENS.TRANSITIONS.DEFAULT}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing('MD') }}>
            <Button
              type="text"
              shape="circle"
              icon={<MenuOutlined />}
              onClick={handleSidebarToggle}
              data-testid="sidebar-toggle-button"
              aria-label={collapsed
                ? t('navigation.expandSidebar', { defaultValue: 'Expand sidebar' })
                : t('navigation.collapseSidebar', { defaultValue: 'Collapse sidebar' })}
              aria-pressed={collapsed}
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 18,
                color: 'var(--color-text-primary)',
              }}
            />
            <div
              style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}
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
                  height: DESIGN_TOKENS.DIMENSIONS.ICON_LG,
                  width: 'auto',
                  objectFit: 'contain',
                  marginTop: -spacing('XS'),
                  marginLeft: -spacing('XS'),
                }}
              />
            </div>
          </div>
          <Space size={spacing('MD')} align="center">
            <NotificationBell />
            <Dropdown
              trigger={['click']}
              placement="bottomRight"
              dropdownRender={() => userMenuOverlay}
              overlayStyle={{ minWidth: 300 }}
            >
              <Button
                type="text"
                aria-label={t('navigation.userMenu', { defaultValue: 'Open user menu' })}
                style={{
                  width: HEADER_ACTION_SIZE,
                  height: HEADER_ACTION_SIZE,
                  borderRadius: borderRadius('FULL'),
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: 0,
                }}
                >
                  <Avatar
                    icon={<UserOutlined />}
                    size={DESIGN_TOKENS.DIMENSIONS.ICON_XL}
                    style={{ backgroundColor: 'var(--color-text-tertiary)' }}
                  />
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content
          className="main-layout-content"
          style={{
            paddingTop: HEADER_HEIGHT + spacing('PAGE_SECTION_GAP'),
            marginRight: contentMargin,
            marginBottom: contentMargin,
            marginLeft: contentMargin + sidebarWidth,
            transition: 'margin-left 0.2s ease',
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
