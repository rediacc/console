import React from 'react';
import { Flex, Layout, Tooltip, Typography } from 'antd';
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

  const isChildActive = (childKey: string) => location.pathname.startsWith(childKey);

  const handleParentClick = (item: MenuItem, visibleChildren: MenuItem[]) => {
    const targetRoute = visibleChildren.length > 0 ? visibleChildren[0]?.key : item.key;
    if (!targetRoute) return;

    onNavigate(targetRoute, {
      menu_item: item.label,
      ui_mode: uiMode,
      sidebar_collapsed: collapsed,
      from_page: location.pathname,
    });
    navigate(targetRoute);
  };

  const handleChildClick = (child: MenuItem, event?: React.MouseEvent) => {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }

    onNavigate(child.key, {
      menu_item: child.label,
      ui_mode: uiMode,
      sidebar_collapsed: collapsed,
      from_page: location.pathname,
    });
    navigate(child.key);
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
        width: sidebarWidth,
      }}
      role="navigation"
      aria-label={t('navigation.mainNavigation')}
      data-testid="main-sidebar"
    >
      <Flex vertical style={{ height: '100%', overflow: 'hidden', paddingTop: isDrawer ? 80 : 16 }}>
        <Flex
          vertical
          style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', paddingBottom: 24 }}
        >
          {menuItems.map((item) => {
            const visibleChildren = item.children || [];
            const hasChildren = visibleChildren.length > 0;
            const isParentActive = hasChildren
              ? visibleChildren.some((child) => isChildActive(child.key))
              : location.pathname.startsWith(item.key);
            const isExpanded = hasChildren
              ? expandedParentKeys.includes(item.key) || isParentActive
              : false;
            const padding = collapsed ? '10px 12px' : '10px 18px';
            const itemKey = item.key || item.label;

            const parentContent = (
              <Flex
                key={itemKey}
                style={{
                  alignItems: 'center',
                  padding,
                  cursor: 'pointer',
                  minHeight: 40,
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  fontWeight: isParentActive ? 600 : 500,
                }}
                onClick={() => handleParentClick(item, visibleChildren)}
                data-testid={`sidebar-menu-${formatKeyForTestId(item.key)}`}
              >
                <Typography.Text
                  style={{
                    fontSize: 16,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 16,
                    height: 16,
                    flexShrink: 0,
                  }}
                >
                  {item.icon}
                </Typography.Text>
                <Typography.Text
                  style={{
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                    textOverflow: 'ellipsis',
                    display: collapsed ? 'none' : 'block',
                    flex: 1,
                  }}
                >
                  {item.label}
                </Typography.Text>
              </Flex>
            );

            if (collapsed) {
              const tooltipContent = hasChildren ? (
                <Flex vertical style={{ padding: 12 }}>
                  {visibleChildren.map((child) => {
                    const childActive = isChildActive(child.key);
                    return (
                      <Flex
                        key={child.key}
                        style={{
                          padding: '12px 16px',
                          fontWeight: childActive ? 600 : 500,
                          cursor: 'pointer',
                          fontSize: 14,
                          minWidth: 160,
                        }}
                        onClick={(event) => handleChildClick(child, event)}
                      >
                        {child.label}
                      </Flex>
                    );
                  })}
                </Flex>
              ) : (
                <Flex vertical style={{ padding: 12 }}>
                  <Flex
                    style={{
                      padding: '12px 16px',
                      fontWeight: isParentActive ? 600 : 500,
                      cursor: 'pointer',
                      fontSize: 14,
                      minWidth: 160,
                    }}
                  >
                    {item.label}
                  </Flex>
                </Flex>
              );

              return (
                <Tooltip
                  key={itemKey}
                  title={tooltipContent}
                  placement="right"
                  overlayInnerStyle={{ padding: 0, background: 'var(--ant-color-bg-container)' }}
                >
                  {parentContent}
                </Tooltip>
              );
            }

            return (
              <Flex vertical key={itemKey}>
                {parentContent}
                {hasChildren && (
                  <Flex
                    vertical
                    style={{
                      padding: '8px 0',
                      overflow: 'hidden',
                      maxHeight: isExpanded ? 320 : 0,
                    }}
                  >
                    {visibleChildren.map((child) => {
                      const childActive = isChildActive(child.key);
                      return (
                        <Flex
                          key={child.key}
                          style={{
                            alignItems: 'center',
                            padding: '12px 24px',
                            fontSize: 14,
                            fontWeight: childActive ? 600 : 500,
                            cursor: 'pointer',
                          }}
                          onClick={() => handleChildClick(child)}
                          data-testid={`sidebar-submenu-${formatKeyForTestId(child.key)}`}
                        >
                          {child.label}
                        </Flex>
                      );
                    })}
                  </Flex>
                )}
              </Flex>
            );
          })}
        </Flex>
      </Flex>
    </Sider>
  );
};
