import styled from 'styled-components';
import { Card, Typography } from 'antd';
import {
  DetailPanelSecondaryTextBlock,
  DetailPanelSurface,
  DetailPanelHeader,
  DetailPanelHeaderRow,
  DetailPanelTitleGroup,
  DetailPanelTitle,
  DetailPanelCollapseButton,
  DetailPanelTagGroup,
  DetailPanelBody,
  DetailPanelSectionHeader,
  DetailPanelSectionTitle,
  DetailPanelSectionCard,
  DetailPanelFieldList,
  DetailPanelFieldRow,
  DetailPanelFieldLabel,
  DetailPanelFieldValue,
  DetailPanelFieldStrongValue,
  DetailPanelFieldMonospaceValue,
  DetailPanelDivider,
} from '../detailPanelPrimitives';

const { Text } = Typography;

export {
  DetailPanelSurface as DetailPanel,
  DetailPanelHeader as Header,
  DetailPanelHeaderRow as HeaderTop,
  DetailPanelTitleGroup as TitleGroup,
  DetailPanelTitle as PanelTitle,
  DetailPanelCollapseButton as CollapseButton,
  DetailPanelTagGroup as TagGroup,
  DetailPanelBody as PanelContent,
  DetailPanelSectionHeader as SectionHeader,
  DetailPanelSectionTitle as SectionTitle,
  DetailPanelSectionCard as SectionCard,
  DetailPanelFieldList as FieldList,
  DetailPanelFieldRow as FieldRow,
  DetailPanelFieldLabel as FieldLabel,
  DetailPanelFieldValue as FieldValue,
  DetailPanelFieldStrongValue as FieldValueStrong,
  DetailPanelFieldMonospaceValue as FieldValueMonospace,
  DetailPanelDivider as SectionDivider,
};

export const DividerLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const MetricCard = styled(Card).attrs({ size: 'small' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const MetricLabel = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MetricValue = styled(Text)<{ $isWarning?: boolean }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme, $isWarning }) => ($isWarning ? theme.colors.error : theme.colors.textPrimary)};
  }
`;

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const InlineText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const SubduedText = styled(DetailPanelSecondaryTextBlock)``;
