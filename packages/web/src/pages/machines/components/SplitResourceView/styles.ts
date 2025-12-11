import styled from 'styled-components';

export const SplitViewContainer = styled.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`;

export const LeftPanel = styled.div<{ $width: string }>`
  width: ${({ $width }) => $width};
  height: 100%;
  overflow: auto;
  min-width: ${({ theme }) => theme.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`;

export const Backdrop = styled.div<{ $visible: boolean; $rightOffset: number }>`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({ $rightOffset }) => `${$rightOffset}px`};
  bottom: 0;
  background-color: ${({ theme }) => theme.overlays.backdrop};
  opacity: ${({ $visible }) => ($visible ? 1 : 0)};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({ theme }) => theme.zIndex.MODAL};
  pointer-events: ${({ $visible }) => ($visible ? 'auto' : 'none')};
`;
