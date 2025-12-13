import styled from 'styled-components';
import { ActionGroup, CenteredState, ContentStack } from '@/components/common/styled';

// Re-export from common/styled
export { ContentStack, ActionGroup };

export const FiltersRow = styled.div`
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const FilterLabel = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const FilterSelectWrapper = styled.div`
  width: 100%;
  min-width: ${({ theme }) => theme.dimensions.POPOVER_WIDTH}px;
`;

export const FilterActions = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: auto;
`;

export const VisualizationContainer = styled.div`
  width: 100%;
  height: ${({ theme }) => theme.dimensions.VISUALIZATION_HEIGHT}px;
  overflow: hidden;
  position: relative;
`;

export const LoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  background-color: ${({ theme }) => theme.overlays.content};
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  z-index: ${({ theme }) => theme.zIndex.DROPDOWN};
`;

export const LoadingMessage = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const VisualizationCanvas = styled.svg`
  width: 100%;
  height: 100%;
`;

export const LegendGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const LegendItem = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const LegendIcon = styled.div<{ $color: string }>`
  width: ${({ theme }) => theme.spacing.LG}px;
  height: ${({ theme }) => theme.spacing.LG}px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  background-color: ${({ $color }) => $color};
`;

export { CenteredState };

export const CenteredMessage = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const PageTitle = styled.div`
  margin: 0;
`;
