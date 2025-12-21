import React, { useMemo } from 'react';
import { Layout, Menu, type MenuProps, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import type { MenuItem } from '@/components/layout/MainLayout/helpers';
import { SIDEBAR_COLLAPSED_WIDTH } from '@/components/layout/MainLayout/types';
import { formatKeyForTestId } from '@/utils/testIdHelpers';

const { Sider } = Layout;

type SidebarProps = {
  collapsed: boolean;
  sidebarWidth: number;
  menuItems: MenuItem[];
  expandedParentKeys: string[];
  uiMode: 'simple' | 'expert';
  onNavigate: (route: string, metadata: Record<string, unknown>) => void;
  isDrawer?: boolean;
};

type AntMenuItem = Required<MenuProps>['items'][number];

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  sidebarWidth,
  menuItems,
  expandedParentKeys,
  uiMode,
  onNavigate,
  isDrawer = false,
}) => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const location = useLocation();

  // Compute selected keys based on current path
  const selectedKeys = useMemo(() => {
    const allKeys: string[] = [];
    menuItems.forEach((item) => {
      allKeys.push(item.key);
      item.children?.forEach((child) => allKeys.push(child.key));
    });

    // Find the most specific matching key
    return allKeys
      .filter((key) => location.pathname.startsWith(key))
      .sort((a, b) => b.length - a.length)
      .slice(0, 1);
  }, [location.pathname, menuItems]);

  // Convert menu items to Ant Design format
  const antMenuItems: AntMenuItem[] = useMemo(() => {
    return menuItems.map((item): AntMenuItem => {
      const hasChildren = item.children && item.children.length > 0;

      if (hasChildren) {
        return {
          key: item.key,
          icon: item.icon,
          label: (
            <Typography.Text data-testid={`sidebar-menu-${formatKeyForTestId(item.key)}`}>
              {item.label}
            </Typography.Text>
          ),
          onTitleClick: () => {
            const firstChild = item.children?.[0];
            if (firstChild) {
              onNavigate(firstChild.key, {
                menu_item: item.label,
                ui_mode: uiMode,
                sidebar_collapsed: collapsed,
                from_page: location.pathname,
              });
              navigate(firstChild.key);
            }
          },
          children: item.children?.map((child) => ({
            key: child.key,
            label: (
              <Typography.Text data-testid={`sidebar-submenu-${formatKeyForTestId(child.key)}`}>
                {child.label}
              </Typography.Text>
            ),
          })),
        };
      }

      return {
        key: item.key,
        icon: item.icon,
        label: (
          <Typography.Text data-testid={`sidebar-menu-${formatKeyForTestId(item.key)}`}>
            {item.label}
          </Typography.Text>
        ),
      };
    });
  }, [menuItems, collapsed, uiMode, location.pathname, navigate, onNavigate]);

  // Handle menu item clicks
  const handleClick: MenuProps['onClick'] = ({ key }) => {
    let clickedLabel = key;
    for (const item of menuItems) {
      if (item.key === key) {
        clickedLabel = item.label;
        break;
      }
      if (item.children) {
        const child = item.children.find((c) => c.key === key);
        if (child) {
          clickedLabel = child.label;
          break;
        }
      }
    }

    onNavigate(key, {
      menu_item: clickedLabel,
      ui_mode: uiMode,
      sidebar_collapsed: collapsed,
      from_page: location.pathname,
    });
    navigate(key);
  };

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={collapsed}
      collapsedWidth={SIDEBAR_COLLAPSED_WIDTH}
      width={sidebarWidth}
      style={{
        position: isDrawer ? 'static' : 'fixed',
        left: 0,
        top: isDrawer ? 0 : 64,
        height: isDrawer ? '100%' : 'calc(100vh - 64px)',
        overflow: 'hidden',
        zIndex: 1000,
      }}
      role="navigation"
      aria-label={t('navigation.mainNavigation')}
      data-testid="main-sidebar"
    >
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={selectedKeys}
        openKeys={collapsed ? [] : expandedParentKeys}
        items={antMenuItems}
        onClick={handleClick}
        inlineCollapsed={collapsed}
        style={{
          height: '100%',
          paddingTop: isDrawer ? 80 : 16,
          borderRight: 0,
        }}
      />
    </Sider>
  );
};
