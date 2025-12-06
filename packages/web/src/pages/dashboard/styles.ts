import styled from 'styled-components';
import { Card, Space, Typography, Badge, Progress, List, Timeline } from 'antd';
import { Link as RouterLink } from 'react-router-dom';
import {
  PageContainer,
  scrollbarStyles,
  SecondaryText,
  FlexRow,
  FlexColumn,
} from '@/styles/primitives';
import {
  ContentStack,
  CenteredState,
  FlexBetween,
  InlineStack,
  StatRow,
  StatLabel as BaseStatLabel,
  StatValue as BaseStatValue,
  Divider,
} from '@/components/common/styled';

const { Text } = Typography;

export const PageWrapper = PageContainer;

// Re-export from common/styled
export { ContentStack, CenteredState, FlexBetween, InlineStack, StatRow, Divider };

export const DashboardCard = styled(Card)`
  width: 100%;
`;

export const SectionDescription = SecondaryText;

export const ResourceTile = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  height: 100%;
  transition: ${({ theme }) => theme.transitions.DEFAULT};

  &:hover {
    box-shadow: ${({ theme }) => theme.shadows.MD};
  }
`;

export const TileHeader = styled(FlexRow).attrs({ $justify: 'space-between', $gap: 'SM' })`
  width: 100%;
`;

export const TileMeta = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const ResourceProgress = styled(Progress)`
  margin: ${({ theme }) => theme.spacing.SM}px 0;
`;

export const SectionLabel = styled(Text)`
  && {
    display: block;
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    letter-spacing: ${({ theme }) => theme.letterSpacing.WIDE};
  }
`;

export const SectionTitle = styled(Typography.Title)`
  && {
    margin: ${({ theme }) => theme.spacing.XS}px 0 ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ScrollContainer = styled.div`
  max-height: 200px;
  overflow-y: auto;
  padding-right: ${({ theme }) => theme.spacing.XS}px;
  ${scrollbarStyles}
`;

export const HorizontalScroll = styled.div`
  width: 100%;
  overflow-x: auto;
`;

export const LicenseItem = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px ${({ theme }) => theme.spacing.MD}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  width: 100%;
`;

export const LicenseHeader = styled(FlexRow).attrs({ $justify: 'space-between', $gap: 'SM' })`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const StatList = styled(Space).attrs({ orientation: 'vertical', size: 'middle' })`
  width: 100%;
`;

// Use base components from common/styled with dashboard-specific variants
export const StatLabel = BaseStatLabel;
export const StatValue = BaseStatValue;

export const InlineLink = styled(RouterLink)`
  color: ${({ theme }) => theme.colors.primary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};

  &:hover {
    color: ${({ theme }) => theme.colors.primaryHover};
  }
`;

export const QueueBadgeRow = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const QueueBadge = styled(Badge)<{ $variant?: 'error' | 'warning' | 'info' | 'muted' }>`
  .ant-scroll-number {
    background-color: ${({ theme, $variant }) => {
      switch ($variant) {
        case 'error':
          return theme.colors.error;
        case 'warning':
          return theme.colors.warning;
        case 'info':
          return theme.colors.info;
        case 'muted':
          return theme.colors.textMuted;
        default:
          return theme.colors.primary;
      }
    }};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const TimelineWrapper = styled(Timeline)`
  width: 100%;
`;

const { Item: AntListItem } = List;

export const BorderlessList = styled(List)`
  width: 100%;

  .ant-list-item {
    padding-left: 0;
    padding-right: 0;
  }
`;

export const BorderlessListItem = styled(AntListItem)`
  && {
    padding-left: 0;
    padding-right: 0;
    border: none;
  }
`;

export const AuditMeta = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export { EmptyStateWrapper as EmptyState } from '@/styles/primitives';

export const SectionFooter = styled(FlexRow).attrs({ $justify: 'space-between' })`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  padding-top: ${({ theme }) => theme.spacing.SM}px;
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const PlanCountBadge = styled(Badge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.textPrimary};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const QuantityBadge = styled(Badge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.success};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;
