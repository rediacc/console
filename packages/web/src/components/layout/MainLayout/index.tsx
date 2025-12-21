import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { MenuDataItem } from '@ant-design/pro-components';
import { ProLayout } from '@ant-design/pro-components';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import apiClient from '@/api/client';
import { useCompanyInfo } from '@/api/queries/dashboard';
import logoBlack from '@/assets/logo_black.png';
import SandboxWarning from '@/components/common/SandboxWarning';
import { useTelemetry } from '@/components/common/TelemetryProvider';
import { featureFlags } from '@/config/featureFlags';
import { useMessage } from '@/hooks';
import { masterPasswordService } from '@/services/masterPasswordService';
import { selectCompany } from '@/store/auth/authSelectors';
import { logout, updateCompany } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { toggleUiMode } from '@/store/ui/uiSlice';
import { clearAuthData, getAuthData, saveAuthData } from '@/utils/auth';
import { MenuOutlined, SafetyCertificateOutlined, SmileOutlined } from '@/utils/optimizedIcons';
import { HeaderActions } from './HeaderActions';
import { filterRouteItems, flattenRoutePaths } from './helpers';
import { getRoutes, RouteItem } from './routes';
import { SIDEBAR_EXPANDED_WIDTH } from './types';

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const queryClient = useQueryClient();
  const company = useSelector(selectCompany);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const { t } = useTranslation('common');
  const message = useMessage();
  const { data: companyData } = useCompanyInfo();
  const { trackUserAction } = useTelemetry();

  // Update company data when it changes
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

  // Keyboard shortcut for power mode
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
  }, [message]);

  // Get routes configuration
  const routes = useMemo(() => getRoutes(t), [t]);

  // Filter menu based on uiMode, plan, feature flags
  const menuDataRender = useCallback(
    (menuData: MenuDataItem[]) => {
      return filterRouteItems(menuData as RouteItem[], uiMode, companyData) as MenuDataItem[];
    },
    [uiMode, companyData]
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
    const nextRoutes = filterRouteItems(routes.routes, newMode, companyData);
    const visiblePaths = flattenRoutePaths(nextRoutes);
    const isCurrentPageVisibleInNewMode = visiblePaths.some((path) =>
      currentPath.startsWith(path)
    );

    if (!isCurrentPageVisibleInNewMode) {
      const firstVisiblePath = visiblePaths[0];
      if (firstVisiblePath) {
        navigate(firstVisiblePath);
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
        siderWidth={SIDEBAR_EXPANDED_WIDTH}
        breakpoint="lg"
        collapsed={collapsed}
        onCollapse={handleCollapse}
        collapsedButtonRender={false}
        // Branding
        logo={logoBlack}
        title={false}
        onMenuHeaderClick={() => {
          trackUserAction('navigation', '/dashboard', {
            trigger: 'logo_click',
            from_page: location.pathname,
          });
          navigate('/dashboard');
        }}
        // Menu
        route={routes}
        location={location}
        menuDataRender={menuDataRender}
        menuItemRender={(item, dom) => {
          if (!item.path) return dom;
          return (
            <Link
              to={item.path}
              onClick={() => {
                trackUserAction('navigation', item.path!, {
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
          if (!item.path || item.routes) return dom;
          return (
            <Link
              to={item.path}
              onClick={() => {
                trackUserAction('navigation', item.path!, {
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
          <Flex align="center" gap={12}>
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => handleCollapse(!collapsed)}
              style={{ width: 40, height: 40, fontSize: 16 }}
              data-testid="sidebar-toggle-button"
              aria-label={
                collapsed ? t('navigation.expandSidebar') : t('navigation.collapseSidebar')
              }
              aria-pressed={collapsed}
            />
            <Flex
              style={{ display: 'inline-flex', alignItems: 'center', cursor: 'pointer' }}
              onClick={() => {
                trackUserAction('navigation', '/dashboard', {
                  trigger: 'logo_click',
                  from_page: location.pathname,
                });
                navigate('/dashboard');
              }}
              data-testid="main-logo-home"
            >
              <img
                src={logoBlack}
                alt="Rediacc Logo"
                style={{ height: 32, width: 'auto', objectFit: 'contain' }}
              />
            </Flex>
          </Flex>
        )}
        actionsRender={() => (
          <HeaderActions onModeToggle={handleModeToggle} onLogout={handleLogout} />
        )}
        // Content
        contentStyle={{ padding: 24 }}
        token={{
          header: {
            heightLayoutHeader: 64,
          },
          sider: {
            colorMenuBackground: '#fff',
          },
        }}
      >
        {isTransitioning ? (
          <Flex
            vertical
            align="center"
            justify="center"
            style={{ minHeight: 240 }}
            data-testid="main-content"
          >
            <Flex style={{ fontSize: 32 }}>
              {uiMode === 'simple' ? <SafetyCertificateOutlined /> : <SmileOutlined />}
            </Flex>
            <Flex style={{ fontSize: 16 }}>
              {t('uiMode.switching', {
                mode: uiMode === 'simple' ? t('uiMode.expert') : t('uiMode.simple'),
              })}
            </Flex>
          </Flex>
        ) : (
          <Outlet />
        )}
      </ProLayout>
    </>
  );
};

export default MainLayout;
