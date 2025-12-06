import styled from 'styled-components';
import { Typography, Timeline } from 'antd';
import { Link as RouterLink } from 'react-router-dom';
import {
  RediaccText as UnifiedText,
  RediaccCard,
  RediaccBadge,
  RediaccProgress,
  RediaccList,
  RediaccStack,
} from '@/components/ui';
import { PageContainer, scrollbarStyles, FlexRow, FlexColumn } from '@/styles/primitives';
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

export const PageWrapper = PageContainer;

// Re-export from common/styled
export { ContentStack, CenteredState, FlexBetween, InlineStack, StatRow, Divider };

export const DashboardCard = styled(RediaccCard)`
  width: 100%;
`;

export const SectionDescription = styled(UnifiedText).attrs({ color: 'secondary' })``;

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

export const TileMeta = styled(UnifiedText).attrs({ color: 'secondary', weight: 'medium' })`
  && {
    display: inline-block;
  }
`;

export const ResourceProgress = styled(RediaccProgress)`
  margin: ${({ theme }) => theme.spacing.SM}px 0;
`;

export const SectionLabel = styled(UnifiedText).attrs({ color: 'secondary', size: 'sm' })`
  && {
    display: block;
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

export const StatList = styled(RediaccStack).attrs({ direction: 'vertical', gap: 'md' })`
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

export const QueueBadge = styled(RediaccBadge)<{
  $variant?: 'error' | 'warning' | 'info' | 'muted';
}>`
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

const { Item: AntListItem } = RediaccList;

export const BorderlessList = styled(RediaccList)`
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

export const AuditMeta = styled(UnifiedText).attrs({ size: 'sm', color: 'secondary' })``;

export const SectionFooter = styled(FlexRow).attrs({ $justify: 'space-between' })`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  padding-top: ${({ theme }) => theme.spacing.SM}px;
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const PlanCountBadge = styled(RediaccBadge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.textPrimary};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const QuantityBadge = styled(RediaccBadge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.success};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;
