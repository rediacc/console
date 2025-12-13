import React from 'react';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import type { MenuItem } from '@/components/layout/MainLayout/helpers';
import { SIDEBAR_COLLAPSED_WIDTH } from '@/components/layout/MainLayout/types';
import {
  MenuIcon,
  MenuLabel,
  MenuScrollArea,
  SidebarContent,
  MenuItem as StyledMenuItem,
  StyledSider,
  SubMenuContainer,
  SubMenuItem,
  TooltipContent,
  TooltipItem,
  TooltipLabel,
} from './styles';

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
    <StyledSider
      trigger={null}
      collapsible
      collapsed={collapsed}
      collapsedWidth={SIDEBAR_COLLAPSED_WIDTH}
      width={sidebarWidth}
      $sidebarWidth={sidebarWidth}
      $isDrawer={isDrawer}
      role="navigation"
      aria-label={t('navigation.mainNavigation')}
      data-testid="main-sidebar"
    >
      <SidebarContent $isDrawer={isDrawer}>
        <MenuScrollArea>
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
              <StyledMenuItem
                key={itemKey}
                $isActive={isParentActive}
                $padding={padding}
                $collapsed={collapsed}
                onClick={() => handleParentClick(item, visibleChildren)}
                data-testid={`sidebar-menu-${item.key.replace(/\//g, '-').replace(/^-/, '')}`}
              >
                <MenuIcon $isActive={isParentActive} $collapsed={collapsed}>
                  {item.icon}
                </MenuIcon>
                <MenuLabel $isActive={isParentActive} $collapsed={collapsed}>
                  {item.label}
                </MenuLabel>
              </StyledMenuItem>
            );

            if (collapsed) {
              const tooltipContent = hasChildren ? (
                <TooltipContent>
                  {visibleChildren.map((child) => {
                    const childActive = isChildActive(child.key);
                    return (
                      <TooltipItem
                        key={child.key}
                        $isActive={childActive}
                        onClick={(event) => handleChildClick(child, event)}
                      >
                        {child.label}
                      </TooltipItem>
                    );
                  })}
                </TooltipContent>
              ) : (
                <TooltipContent>
                  <TooltipLabel $isActive={isParentActive}>{item.label}</TooltipLabel>
                </TooltipContent>
              );

              return (
                <Tooltip
                  key={itemKey}
                  title={tooltipContent}
                  placement="right"
                  color="var(--color-bg-primary)"
                  overlayInnerStyle={{ padding: 0 }}
                >
                  {parentContent}
                </Tooltip>
              );
            }

            return (
              <div key={itemKey}>
                {parentContent}
                {hasChildren && (
                  <SubMenuContainer $isExpanded={isExpanded}>
                    {visibleChildren.map((child) => {
                      const childActive = isChildActive(child.key);
                      return (
                        <SubMenuItem
                          key={child.key}
                          $isActive={childActive}
                          onClick={() => handleChildClick(child)}
                          data-testid={`sidebar-submenu-${child.key.replace(/\//g, '-').replace(/^-/, '')}`}
                        >
                          {child.label}
                        </SubMenuItem>
                      );
                    })}
                  </SubMenuContainer>
                )}
              </div>
            );
          })}
        </MenuScrollArea>
      </SidebarContent>
    </StyledSider>
  );
};
