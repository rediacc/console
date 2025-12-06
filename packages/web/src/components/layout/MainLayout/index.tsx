import React, { useState, useEffect, useMemo } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { Layout, Dropdown, message, Drawer } from 'antd';
import {
  UserOutlined,
  MenuOutlined,
  SmileOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { selectUser, selectCompany } from '@/store/auth/authSelectors';
import { logout, updateCompany } from '@/store/auth/authSlice';
import { masterPasswordService } from '@/services/masterPasswordService';
import { toggleUiMode } from '@/store/ui/uiSlice';
import { clearAuthData, saveAuthData, getAuthData } from '@/utils/auth';
import apiClient from '@/api/client';
import NotificationBell from '@/components/layout/MainLayout/components/NotificationBell';
import { useTheme } from '@/context/ThemeContext';
import logoBlack from '@/assets/logo_black.png';
import logoWhite from '@/assets/logo_white.png';
import { RootState } from '@/store/store';
import { useCompanyInfo } from '@/api/queries/dashboard';
import { useQueryClient } from '@tanstack/react-query';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import SandboxWarning from '@/components/common/SandboxWarning';
import { useTelemetry } from '@/components/common/TelemetryProvider';
import { featureFlags } from '@/config/featureFlags';
import { getMenuItems } from './menuItems';
import { buildMenuItems, flattenMenuRoutes } from './helpers';
import { UserMenu } from './UserMenu';
import { Sidebar } from './Sidebar';
import { SIDEBAR_EXPANDED_WIDTH, SIDEBAR_COLLAPSED_WIDTH } from './types';
import {
  HEADER_HEIGHT,
  MainLayoutContainer,
  StyledHeader,
  HeaderLeft,
  HeaderRight,
  MenuToggleButton,
  LogoWrapper,
  Logo,
  StyledContent,
  TransitionOverlay,
  TransitionIcon,
  TransitionText,
  ContentWrapper,
} from './styles';
import { RediaccButton } from '@/components/ui';

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [expandedParentKeys, setExpandedParentKeys] = useState<string[]>([]);
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const queryClient = useQueryClient();
  const user = useSelector(selectUser);
  const company = useSelector(selectCompany);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const { theme } = useTheme();
  const { t } = useTranslation('common');
  const { data: companyData } = useCompanyInfo();
  const { trackUserAction } = useTelemetry();

  useEffect(() => {
    const updateCompanyData = async () => {
      const normalizedCompanyName = companyData?.companyInfo?.companyName;
      if (normalizedCompanyName && normalizedCompanyName !== company) {
        dispatch(updateCompany(normalizedCompanyName));
        const authData = await getAuthData();
        if (authData.email) {
          await saveAuthData(authData.email, normalizedCompanyName);
        }
      }
    };
    updateCompanyData();
  }, [companyData, company, dispatch]);

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'E') {
        e.preventDefault();
        const onLocalhost =
          window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        const newState = featureFlags.togglePowerMode();
        const msg = onLocalhost
          ? newState
            ? 'Localhost Mode - All features enabled'
            : 'Localhost Mode - All features disabled'
          : newState
            ? 'Advanced options enabled'
            : 'Advanced options disabled';
        message.info(msg);
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  const allMenuItems = useMemo(() => getMenuItems(t), [t]);
  const menuItems = useMemo(
    () => buildMenuItems(allMenuItems, uiMode, companyData),
    [allMenuItems, uiMode, companyData]
  );

  const handleModeToggle = () => {
    setIsTransitioning(true);
    dispatch(toggleUiMode());
    const newMode = uiMode === 'simple' ? 'expert' : 'simple';
    trackUserAction('ui_mode_toggle', 'mode_switcher', {
      from_mode: uiMode,
      to_mode: newMode,
      current_page: location.pathname,
    });

    const currentPath = location.pathname;
    const nextMenuItems = buildMenuItems(allMenuItems, newMode, companyData);
    const visibleRoutes = flattenMenuRoutes(nextMenuItems);
    const isCurrentPageVisibleInNewMode = visibleRoutes.some((route) =>
      currentPath.startsWith(route)
    );

    if (!isCurrentPageVisibleInNewMode) {
      const firstVisibleRoute = visibleRoutes[0];
      if (firstVisibleRoute) {
        navigate(firstVisibleRoute);
      }
    }
    setIsTransitioning(false);
  };

  const handleLogout = async () => {
    trackUserAction('logout', 'logout_button', {
      current_page: location.pathname,
      session_duration:
        Date.now() - ((window as Window & { sessionStartTime?: number }).sessionStartTime || 0),
    });
    try {
      await apiClient.logout();
    } catch {
      // Continue with logout even if API call fails
    }
    await clearAuthData();
    masterPasswordService.clearMasterPassword();
    queryClient.clear();
    dispatch(logout());
    navigate('/login');
  };

  const handleSidebarToggle = () => {
    // Toggle drawer on mobile, collapse sidebar on desktop
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
      setMobileMenuOpen((prev) => !prev);
      trackUserAction('ui_interaction', 'mobile_menu_toggle', {
        current_page: location.pathname,
      });
    } else {
      const action = collapsed ? 'sidebar_expand' : 'sidebar_collapse';
      trackUserAction('ui_interaction', action, {
        current_page: location.pathname,
      });
      setCollapsed((prev) => !prev);
    }
  };

  const handleMobileMenuClose = () => {
    setMobileMenuOpen(false);
  };

  const handleNavigate = (route: string, metadata: Record<string, unknown>) => {
    trackUserAction('navigation', route, metadata as Record<string, string | number | boolean>);
  };

  useEffect(() => {
    const activeParents = menuItems
      .filter((item) => item.children)
      .filter((item) => item.children?.some((child) => location.pathname.startsWith(child.key)))
      .map((item) => item.key);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExpandedParentKeys(activeParents);
  }, [location.pathname, menuItems]);

  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH;
  const contentPaddingTop = HEADER_HEIGHT + DESIGN_TOKENS.SPACING.PAGE_SECTION_GAP;

  return (
    <>
      <SandboxWarning />
      <MainLayoutContainer>
        {/* Desktop Sidebar */}
        <Sidebar
          collapsed={collapsed}
          sidebarWidth={sidebarWidth}
          menuItems={menuItems}
          expandedParentKeys={expandedParentKeys}
          uiMode={uiMode}
          onNavigate={handleNavigate}
        />

        {/* Mobile Drawer */}
        <Drawer
          title={null}
          placement="left"
          onClose={handleMobileMenuClose}
          open={mobileMenuOpen}
          width={280}
          styles={{
            body: { padding: 0, backgroundColor: 'var(--color-bg-primary)' },
            header: { display: 'none' },
          }}
        >
          <Sidebar
            collapsed={false}
            sidebarWidth={280}
            menuItems={menuItems}
            expandedParentKeys={expandedParentKeys}
            uiMode={uiMode}
            isDrawer={true}
            onNavigate={(route, metadata) => {
              handleNavigate(route, metadata);
              handleMobileMenuClose();
            }}
          />
        </Drawer>

        <Layout>
          <StyledHeader $isDark={theme === 'dark'}>
            <HeaderLeft>
              <MenuToggleButton
                iconOnly
                icon={<MenuOutlined />}
                onClick={handleSidebarToggle}
                data-testid="sidebar-toggle-button"
                aria-label={
                  collapsed
                    ? t('navigation.expandSidebar', { defaultValue: 'Expand sidebar' })
                    : t('navigation.collapseSidebar', { defaultValue: 'Collapse sidebar' })
                }
                aria-pressed={collapsed}
                style={{ borderRadius: '50%', width: '40px', height: '40px' }}
              />
              <LogoWrapper
                onClick={() => {
                  trackUserAction('navigation', '/dashboard', {
                    trigger: 'logo_click',
                    from_page: location.pathname,
                  });
                  navigate('/dashboard');
                }}
                data-testid="main-logo-home"
              >
                <Logo src={theme === 'dark' ? logoWhite : logoBlack} alt="Rediacc Logo" />
              </LogoWrapper>
            </HeaderLeft>
            <HeaderRight>
              <NotificationBell />
              <Dropdown
                trigger={['click']}
                placement="bottomRight"
                popupRender={() => (
                  <UserMenu
                    user={user}
                    company={company}
                    companyData={companyData}
                    uiMode={uiMode}
                    onModeToggle={handleModeToggle}
                    onLogout={handleLogout}
                  />
                )}
                overlayStyle={{ minWidth: 300 }}
              >
                <RediaccButton
                  variant="primary"
                  iconOnly
                  icon={<UserOutlined />}
                  aria-label={t('navigation.userMenu', { defaultValue: 'Open user menu' })}
                  data-testid="user-menu-button"
                  style={{ borderRadius: '50%', width: '40px', height: '40px' }}
                />
              </Dropdown>
            </HeaderRight>
          </StyledHeader>
          <StyledContent $marginLeft={sidebarWidth} $paddingTop={contentPaddingTop}>
            {isTransitioning ? (
              <TransitionOverlay>
                <TransitionIcon>
                  {uiMode === 'simple' ? <SafetyCertificateOutlined /> : <SmileOutlined />}
                </TransitionIcon>
                <TransitionText>
                  {t('uiMode.switching', {
                    mode: uiMode === 'simple' ? t('uiMode.expert') : t('uiMode.simple'),
                  })}
                </TransitionText>
              </TransitionOverlay>
            ) : (
              <ContentWrapper>
                <Outlet />
              </ContentWrapper>
            )}
          </StyledContent>
        </Layout>
      </MainLayoutContainer>
    </>
  );
};

export default MainLayout;
