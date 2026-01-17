import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ProLayout } from '@ant-design/pro-components';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex, Grid } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import apiClient from '@/api/client';
import { useOrganizationInfo } from '@/api/hooks-organization';
import logoBlack from '@/assets/logo_black.png';
import logoWhite from '@/assets/logo_white.png';
import SandboxWarning from '@/components/common/SandboxWarning';
import { useTelemetry } from '@/components/common/TelemetryProvider';
import { featureFlags } from '@/config/featureFlags';
import { useMessage } from '@/hooks';
import { masterPasswordService } from '@/services/auth';
import { selectOrganization } from '@/store/auth/authSelectors';
import { logout, updateOrganization } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { toggleThemeMode, toggleUiMode } from '@/store/ui/uiSlice';
import { clearAuthData, getAuthData, saveAuthData } from '@/utils/auth';
import { MenuOutlined, SafetyCertificateOutlined, SmileOutlined } from '@/utils/optimizedIcons';
import { HeaderActions } from './HeaderActions';
import { filterRouteItems, flattenRoutePaths } from './helpers';
import { getRoutes, RouteItem } from './routes';
import { SIDEBAR_EXPANDED_WIDTH } from './types';
import type { MenuDataItem } from '@ant-design/pro-components';

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const queryClient = useQueryClient();
  const organization = useSelector(selectOrganization);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const logo = themeMode === 'dark' ? logoWhite : logoBlack;
  const { t } = useTranslation('common');
  const message = useMessage();
  const { data: organizationData } = useOrganizationInfo();
  const { trackUserAction } = useTelemetry();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;

  // Update organization data when it changes
  useEffect(() => {
    const updateOrganizationData = async () => {
      const normalizedOrganizationName = organizationData?.organizationInfo?.organizationName;
      if (normalizedOrganizationName && normalizedOrganizationName !== organization) {
        dispatch(updateOrganization(normalizedOrganizationName));
        const authData = await getAuthData();
        if (authData.email) {
          await saveAuthData(authData.email, normalizedOrganizationName);
        }
      }
    };
    void updateOrganizationData();
  }, [organizationData, organization, dispatch]);

  // Helper to get power mode message
  const getPowerModeMessage = useCallback(
    (newState: boolean, onLocalhost: boolean): string => {
      if (onLocalhost) {
        return newState ? t('powerMode.localhostAllEnabled') : t('powerMode.localhostAllDisabled');
      }
      return newState ? t('powerMode.advancedEnabled') : t('powerMode.advancedDisabled');
    },
    [t]
  );

  // Keyboard shortcut for power mode
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!e.ctrlKey || !e.shiftKey || e.key !== 'E') return;
      e.preventDefault();
      const onLocalhost =
        window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const newState = featureFlags.togglePowerMode();
      message.info(getPowerModeMessage(newState, onLocalhost));
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [message, getPowerModeMessage]);

  // Get routes configuration
  const routes = useMemo(() => getRoutes(t), [t]);

  // Filter menu based on uiMode, plan, feature flags
  const menuDataRender = useCallback(
    (menuData: MenuDataItem[]) => {
      return filterRouteItems(menuData as RouteItem[], uiMode, organizationData) as MenuDataItem[];
    },
    [uiMode, organizationData]
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

    // Check if current page is visible in new mode
    const currentPath = location.pathname;
    const nextRoutes = filterRouteItems(routes.routes, newMode, organizationData);
    const visiblePaths = flattenRoutePaths(nextRoutes);
    const isCurrentPageVisibleInNewMode = visiblePaths.some((path) => currentPath.startsWith(path));

    if (!isCurrentPageVisibleInNewMode) {
      const firstVisiblePath = visiblePaths[0];
      if (firstVisiblePath) {
        void navigate(firstVisiblePath);
      }
    }
    setIsTransitioning(false);
  };

  const handleThemeToggle = () => {
    dispatch(toggleThemeMode());
  };

  const handleLogout = () => {
    trackUserAction('logout', 'logout_button', {
      current_page: location.pathname,
      session_duration:
        Date.now() - ((window as Window & { sessionStartTime?: number }).sessionStartTime ?? 0),
    });
    void (async () => {
      try {
        await apiClient.logout();
      } catch {
        // Continue with logout even if API call fails
      }
      await clearAuthData();
      masterPasswordService.clearMasterPassword();
      queryClient.clear();
      dispatch(logout());
      void navigate('/login');
    })();
  };

  const handleCollapse = (value: boolean) => {
    const action = value ? 'sidebar_collapse' : 'sidebar_expand';
    trackUserAction('ui_interaction', action, {
      current_page: location.pathname,
    });
    setCollapsed(value);
  };

  return (
    <>
      <SandboxWarning />
      <ProLayout
        layout="side"
        fixSiderbar
        fixedHeader
        contentWidth="Fluid"
        siderWidth={SIDEBAR_EXPANDED_WIDTH}
        breakpoint="lg"
        collapsed={collapsed}
        onCollapse={handleCollapse}
        collapsedButtonRender={false}
        // Branding
        logo={collapsed ? false : logo}
        title={false}
        onMenuHeaderClick={() => {
          trackUserAction('navigation', '/dashboard', {
            trigger: 'logo_click',
            from_page: location.pathname,
          });
          void navigate('/dashboard');
        }}
        // Menu
        route={routes}
        location={location}
        menuDataRender={menuDataRender}
        menuItemRender={(item, dom) => {
          if (!item.path) return dom;
          const navKey = item.path.replace(/^\//, '').replaceAll('/', '-') || 'home';
          return (
            <Link
              to={item.path}
              data-testid={`main-nav-${navKey}`}
              onClick={() => {
                trackUserAction('navigation', item.path, {
                  menu_item: item.name as string,
                  ui_mode: uiMode,
                  sidebar_collapsed: collapsed,
                  from_page: location.pathname,
                });
              }}
            >
              {dom}
            </Link>
          );
        }}
        subMenuItemRender={(item, dom) => {
          if (!item.path) return dom;
          const navKey = item.path.replace(/^\//, '').replaceAll('/', '-') || 'home';
          return (
            <Link
              to={item.path}
              data-testid={`main-nav-${navKey}`}
              onClick={() => {
                trackUserAction('navigation', item.path, {
                  menu_item: item.name as string,
                  ui_mode: uiMode,
                  sidebar_collapsed: collapsed,
                  from_page: location.pathname,
                });
              }}
            >
              {dom}
            </Link>
          );
        }}
        // Header
        headerTitleRender={() => (
          <Flex align="center">
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => handleCollapse(!collapsed)}
              data-testid="sidebar-toggle-button"
              aria-label={
                collapsed ? t('navigation.expandSidebar') : t('navigation.collapseSidebar')
              }
              aria-pressed={collapsed}
            />
            <Flex
              align="center"
              className="inline-flex cursor-pointer"
              onClick={() => {
                trackUserAction('navigation', '/dashboard', {
                  trigger: 'logo_click',
                  from_page: location.pathname,
                });
                void navigate('/dashboard');
              }}
              data-testid="main-logo-home"
            >
              <img
                src={logo}
                alt={t('common:alt.logo')}
                className={isMobile ? 'h-6 w-auto object-contain' : 'h-8 w-auto object-contain'}
              />
            </Flex>
          </Flex>
        )}
        actionsRender={() => (
          <HeaderActions
            onModeToggle={handleModeToggle}
            onThemeToggle={handleThemeToggle}
            onLogout={handleLogout}
          />
        )}
        // Content
        contentStyle={undefined}
        token={{
          header: {
            heightLayoutHeader: 64,
          },
        }}
      >
        <Flex vertical data-testid="main-content">
          {isTransitioning ? (
            <Flex
              vertical
              align="center"
              justify="center"
              className="min-h-[240px]"
            >
              <Flex>{uiMode === 'simple' ? <SafetyCertificateOutlined /> : <SmileOutlined />}</Flex>
              <Flex>
                {t('uiMode.switching', {
                  mode: uiMode === 'simple' ? t('uiMode.expert') : t('uiMode.simple'),
                })}
              </Flex>
            </Flex>
          ) : (
            <Outlet />
          )}
        </Flex>
      </ProLayout>
    </>
  );
};

export default MainLayout;
