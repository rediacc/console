import styled from 'styled-components';
import { Space, Typography } from 'antd';
import { PageContainer, SectionHeaderRow } from '@/styles/primitives';

export const PageWrapper = PageContainer;

export const ContentStack = styled(Space).attrs({ orientation: 'vertical', size: 'large' })`
  width: 100%;
`;

export const HeaderStack = styled(Space).attrs({ orientation: 'vertical', size: 'middle' })`
  width: 100%;
`;

export const HeaderRow = SectionHeaderRow;

export const ActionGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
`;

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
  min-width: 400px;
`;

export const FilterActions = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: auto;
`;

export const VisualizationContainer = styled.div`
  width: 100%;
  height: 600px;
  overflow: hidden;
  position: relative;
`;

export const LoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  background-color: rgba(255, 255, 255, 0.85);
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
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const LegendItem = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const LegendIcon = styled.div<{ $color: string }>`
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  background-color: ${({ $color }) => $color};
`;

const { Title } = Typography;

export const SectionTitleText = styled(Title)`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const CenteredState = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing['6']}px;
`;

export const CenteredMessage = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;
