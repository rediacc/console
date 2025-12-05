import styled from 'styled-components';
import { Card, Button, Input, Tag, Statistic, Typography } from 'antd';
import {
  TableContainer as BaseTableContainer,
  CardTitle as PrimitiveCardTitle,
} from '@/styles/primitives';

const { Text } = Typography;

export const TabContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const StyledCard = styled(Card)`
  border: 1px solid var(--color-border-secondary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

export const StatCard = styled(StyledCard)`
  min-height: 100%;
`;

export const StatTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const StatMetric = styled(Statistic)<{ $color?: string }>`
  && .ant-statistic-content-value {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ $color }) => $color || 'var(--color-text-primary)'};
  }
`;

export const StatSuffix = styled.span`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const TableCard = styled(StyledCard)``;

export const CardTitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const CardTitleText = PrimitiveCardTitle;

export const RefreshButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: ${({ theme }) => theme.spacing['5']}px;
    min-height: ${({ theme }) => theme.spacing['5']}px;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
  }
`;

export const SearchInput = styled(Input)`
  && {
    width: min(320px, 100%);
  }
`;

export const TableWrapper = styled(BaseTableContainer)``;

export const SessionTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  padding: 0 ${({ theme }) => theme.spacing.XS}px;
`;

export const CellText = styled.span<{ $muted?: boolean }>`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ $muted, theme }) => ($muted ? theme.colors.textTertiary : theme.colors.textPrimary)};
`;

export const SummaryText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;
