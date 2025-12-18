import styled from 'styled-components';
import {
  CollapseButton,
  ContentWrapper,
  FieldLabel,
  FieldList,
  FieldRow,
  FieldValue,
  FieldValueMonospace,
  FieldValueStrong,
  Header,
  HeaderRow,
  PanelTitle,
  PanelWrapper,
  SectionCard,
  SectionDivider,
  SectionHeader,
  SectionTitle,
  TagGroup,
  TitleGroup,
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
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH_SM}px, 1fr));
`;

export const MetricCard = styled(RediaccCard).attrs({ size: 'sm' })`
  && {
  }
`;

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
`;
