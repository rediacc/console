import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';
import type { StyledTheme } from '@/styles/styledTheme';

type ResourceType = 'machine' | 'repository' | 'container';

const resourceColor = (type: ResourceType, theme: StyledTheme) => {
  switch (type) {
    case 'machine':
      return theme.colors.secondary;
    case 'repository':
      return theme.colors.success;
    case 'container':
    default:
      return theme.colors.primary;
  }
};

export const PanelContainer = styled.div<{ $width: number; $opacity: number }>`
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: ${({ $width }) => `${$width}px`};
  border-left: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  display: flex;
  flex-shrink: 0;
  opacity: ${({ $opacity }) => $opacity};
  transition: width 0.3s ease-in-out, opacity 0.3s ease;
  z-index: ${({ theme }) => theme.zIndex.MODAL};
`;

export const ResizeHandle = styled.div`
  position: absolute;
  left: -3px;
  top: 0;
  bottom: 0;
  width: ${({ theme }) => theme.dimensions.SCROLLBAR_WIDTH}px;
  cursor: ew-resize;
  z-index: ${({ theme }) => theme.zIndex.STICKY};
  background-color: transparent;
`;

export const ResizeIndicator = styled.div`
  position: absolute;
  left: ${({ theme }) => theme.dimensions.SCROLLBAR_WIDTH_THIN}px;
  top: 0;
  bottom: 0;
  width: ${({ theme }) => theme.dimensions.SCROLLBAR_WIDTH_THIN}px;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
  transition: background-color ${({ theme }) => theme.transitions.FAST};

  ${ResizeHandle}:hover & {
    background-color: ${({ theme }) => theme.colors.primary};
  }
`;

export const CollapsedPanel = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
  padding: ${({ theme }) => theme.spacing.MD}px 0;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const ToggleButton = styled(RediaccButton).attrs({ iconOnly: true })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const CollapsedIcon = styled.span<{ $type: ResourceType }>`
  font-size: ${({ theme }) => theme.fontSize.XL}px;
  color: ${({ theme, $type }) => resourceColor($type, theme)};
`;

export const ExpandedContent = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
`;
