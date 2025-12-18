import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';

type ResourceType = 'machine' | 'repository' | 'container';

export const PanelContainer = styled.div<{ $width: number }>`
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: ${({ $width }) => `${$width}px`};
  display: flex;
  flex-shrink: 0;
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
`;

export const ResizeIndicator = styled.div`
  position: absolute;
  left: ${({ theme }) => theme.dimensions.SCROLLBAR_WIDTH_THIN}px;
  top: 0;
  bottom: 0;
  width: ${({ theme }) => theme.dimensions.SCROLLBAR_WIDTH_THIN}px;

  ${ResizeHandle}:hover & {
  }
`;

export const CollapsedPanel = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
`;

export const ToggleButton = styled(RediaccButton).attrs({ iconOnly: true })`
  && {
  }
`;

export const CollapsedIcon = styled.span<{ $type: ResourceType }>`
  font-size: ${({ theme }) => theme.fontSize.XL}px;
`;

export const ExpandedContent = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
`;
