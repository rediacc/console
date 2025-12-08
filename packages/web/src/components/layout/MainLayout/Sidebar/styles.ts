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
  border-right: none;
  box-shadow: none;
  transition: left ${DESIGN_TOKENS.TRANSITIONS.SLOW}, width ${DESIGN_TOKENS.TRANSITIONS.DEFAULT};

  /* Hide sidebar on mobile - use drawer only */
  @media (max-width: 768px) {
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
  margin: ${({ $collapsed }) => ($collapsed ? '4px' : '4px 12px')};
  border-radius: ${({ theme }) => theme.borderRadius.XL}px;
  cursor: pointer;
  min-height: 44px;
  justify-content: ${({ $collapsed }) => ($collapsed ? 'center' : 'flex-start')};
  background-color: ${({ $isActive }) => ($isActive ? 'var(--color-bg-selected)' : 'transparent')};
  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-text-selected)' : 'var(--color-text-primary)'};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  transition: all 0.2s ease;

  &:hover {
    background-color: ${({ $isActive }) =>
      $isActive ? 'var(--color-bg-selected)' : 'var(--color-bg-hover)'};
  }
`;

export const MenuIcon = styled.span<{ $isActive: boolean; $collapsed?: boolean }>`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  margin-right: ${({ $collapsed }) => ($collapsed ? '0' : '12px')};
  color: ${({ $isActive }) => ($isActive ? 'var(--color-text-selected)' : 'inherit')};
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: ${({ theme }) => theme.dimensions.ICON_MD}px;
  height: ${({ theme }) => theme.dimensions.ICON_MD}px;
  flex-shrink: 0;
`;

export const MenuLabel = styled.span<{ $isActive: boolean; $collapsed: boolean }>`
  margin-left: 8px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-text-selected)' : 'var(--color-text-primary)'};
  display: ${({ $collapsed }) => ($collapsed ? 'none' : 'block')};
  transition: opacity 0.2s ease;
  flex: 1;
`;

export const TooltipContent = styled(FlexColumn).attrs({ $gap: 'XS' })`
  background-color: var(--color-bg-primary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  border: 1px solid var(--color-border-secondary);
`;

export const TooltipItem = styled.div<{ $isActive: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;

  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-text-selected)' : 'var(--color-text-primary)'};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  cursor: pointer;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  min-width: 160px;
  transition: all 0.2s ease;

  &:hover {
    background-color: ${({ $isActive }) =>
      $isActive ? 'var(--color-bg-selected)' : 'var(--color-bg-hover)'};
  }
`;

export const TooltipLabel = styled.div<{ $isActive: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-text-selected)' : 'var(--color-text-primary)'};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  min-width: 160px;
`;

export const SubMenuContainer = styled.div<{ $isExpanded: boolean }>`
  margin: 2px 12px 0 40px;
  padding: ${({ theme }) => `${theme.spacing.XS}px 0`};
  overflow: hidden;
  max-height: ${({ $isExpanded }) => ($isExpanded ? '400px' : '0')};
  transition: max-height ${DESIGN_TOKENS.TRANSITIONS.DEFAULT},
    opacity ${DESIGN_TOKENS.TRANSITIONS.DEFAULT};
  opacity: ${({ $isExpanded }) => ($isExpanded ? 1 : 0)};
`;

export const SubMenuItem = styled.div<{ $isActive: boolean }>`
  display: flex;
  align-items: center;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.LG}px`};
  margin: 2px 0;
  border-radius: ${({ theme }) => theme.borderRadius.XL}px;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-text-selected)' : 'var(--color-text-secondary)'};
  font-weight: ${({ $isActive }) => ($isActive ? 600 : 500)};
  cursor: pointer;
  background-color: ${({ $isActive }) => ($isActive ? 'var(--color-bg-selected)' : 'transparent')};
  transition: background-color ${DESIGN_TOKENS.TRANSITIONS.DEFAULT},
    color ${DESIGN_TOKENS.TRANSITIONS.DEFAULT};

  &:hover {
    background-color: ${({ $isActive }) =>
      $isActive ? 'var(--color-bg-selected)' : 'var(--color-bg-hover)'};
  }
`;
