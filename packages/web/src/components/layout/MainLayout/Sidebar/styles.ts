import { Layout } from 'antd';
import styled from 'styled-components';
import { FlexColumn } from '@/styles/primitives';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const { Sider } = Layout;

export const StyledSider = styled(Sider)<{ $sidebarWidth: number; $isDrawer?: boolean }>`
  position: ${({ $isDrawer }) => ($isDrawer ? 'static' : 'fixed')};
  left: 0;
  top: ${({ $isDrawer }) => ($isDrawer ? '0' : `${DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT}px`)};
  height: ${({ $isDrawer }) =>
    $isDrawer ? '100%' : `calc(100vh - ${DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT}px)`};
  overflow: hidden;
  z-index: ${DESIGN_TOKENS.Z_INDEX.DROPDOWN - 1};
  width: ${({ $sidebarWidth }) => $sidebarWidth}px;

  /* Hide sidebar on mobile - use drawer only */
  @media (max-width: ${({ theme }) => theme.breakpoints.TABLET}px) {
    display: ${({ $isDrawer }) => ($isDrawer ? 'block' : 'none')};
  }
`;

export const SidebarContent = styled(FlexColumn)<{ $isDrawer?: boolean }>`
  height: 100%;
  overflow: hidden;
  padding-top: ${({ theme, $isDrawer }) =>
    $isDrawer
      ? `${DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT + theme.spacing.MD}px`
      : `${theme.spacing.MD}px`};
`;

export const MenuScrollArea = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const MenuItem = styled.div<{ $isActive: boolean; $padding: string; $collapsed?: boolean }>`
  display: flex;
  align-items: center;
  padding: ${({ $padding }) => $padding};
  cursor: pointer;
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  justify-content: ${({ $collapsed }) => ($collapsed ? 'center' : 'flex-start')};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
`;

export const MenuIcon = styled.span<{ $isActive: boolean; $collapsed?: boolean }>`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: ${({ theme }) => theme.dimensions.ICON_MD}px;
  height: ${({ theme }) => theme.dimensions.ICON_MD}px;
  flex-shrink: 0;
`;

export const MenuLabel = styled.span<{ $isActive: boolean; $collapsed: boolean }>`
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  display: ${({ $collapsed }) => ($collapsed ? 'none' : 'block')};
  flex: 1;
`;

export const TooltipContent = styled(FlexColumn).attrs({})`
  padding: ${({ theme }) => theme.spacing.SM}px;
`;

export const TooltipItem = styled.div<{ $isActive: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  cursor: pointer;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  min-width: ${({ theme }) => theme.dimensions.TOOLTIP_MIN_WIDTH}px;
`;

export const TooltipLabel = styled.div<{ $isActive: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  min-width: ${({ theme }) => theme.dimensions.TOOLTIP_MIN_WIDTH}px;
`;

export const SubMenuContainer = styled.div<{ $isExpanded: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.XS}px 0`};
  overflow: hidden;
  max-height: ${({ theme, $isExpanded }) => ($isExpanded ? `${theme.dimensions.LIST_MAX_HEIGHT}px` : '0')};
`;

export const SubMenuItem = styled.div<{ $isActive: boolean }>`
  display: flex;
  align-items: center;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.LG}px`};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  cursor: pointer;
`;
