import styled from 'styled-components';
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
} from '@/components/resources/internal/sharedDetailPanelAliases';
import { RediaccCard } from '@/components/ui';

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

export const MetricCard = styled(RediaccCard).attrs({ size: 'sm' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;
