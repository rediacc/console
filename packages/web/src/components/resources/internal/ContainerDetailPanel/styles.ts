import styled from 'styled-components';
import { RediaccText } from '@/components/ui/Text';
import { RediaccCard } from '@/components/ui';
import {
  PanelWrapper,
  Header,
  HeaderRow,
  TitleGroup,
  PanelTitle,
  CollapseButton,
  TagGroup,
  ContentWrapper,
  SectionHeader,
  SectionTitle,
  SectionCard,
  FieldList,
  FieldRow,
  FieldLabel,
  FieldValue,
  FieldValueStrong,
  FieldValueMonospace,
  SectionDivider,
  SubduedText,
} from '../sharedDetailPanelAliases';

export {
  PanelWrapper,
  Header,
  HeaderRow,
  TitleGroup,
  PanelTitle,
  CollapseButton,
  TagGroup,
  ContentWrapper,
  SectionHeader,
  SectionTitle,
  SectionCard,
  FieldList,
  FieldRow,
  FieldLabel,
  FieldValue,
  FieldValueStrong,
  FieldValueMonospace,
  SectionDivider,
  SubduedText,
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

export const MetricCard = styled(RediaccCard).attrs({ size: 'small' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const MetricLabel = styled(RediaccText).attrs({
  size: 'sm',
  color: 'secondary',
})``;

export const MetricValue = styled(RediaccText).attrs<{ $isWarning?: boolean }>(
  ({ $isWarning }) => ({
    size: 'lg',
    weight: 'semibold',
    color: $isWarning ? 'danger' : 'primary',
  })
)<{ $isWarning?: boolean }>``;

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const InlineText = styled(RediaccText).attrs({
  size: 'sm',
})`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;
