import { Timeline, Typography } from 'antd';
import { Link as RouterLink } from 'react-router-dom';
import styled from 'styled-components';
import {
  CenteredState,
  ContentStack,
  Divider,
  FlexBetween,
  InlineStack,
  StatRow,
} from '@/components/common/styled';
import { RediaccBadge, RediaccList, RediaccProgress, RediaccText } from '@/components/ui';
import {
  StatValue as BaseStatValue,
  FlexColumn,
  FlexRow,
  scrollbarStyles,
} from '@/styles/primitives';
import type { StyledTheme } from '@/styles/styledTheme';

// Re-export from common/styled
export { ContentStack, CenteredState, FlexBetween, InlineStack, StatRow, Divider };

export const ResourceTile = styled.div`
  height: 100%;

  &:hover {
  }
`;

export const TileHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
  width: 100%;
`;

export const TileMeta = styled(RediaccText).attrs({ color: 'secondary', weight: 'medium' })`
  && {
    display: inline-block;
  }
`;

export const ResourceProgress = styled(RediaccProgress)`
`;

export const SectionLabelWrapper = styled.div`
  letter-spacing: ${({ theme }) => theme.letterSpacing.WIDE};
  display: block;
`;

export const SectionTitleWrapper = styled(Typography.Title)`
  && {
  }
`;

export const ScrollContainer = styled.div`
  max-height: ${({ theme }) => theme.dimensions.DASHBOARD_SECTION_HEIGHT}px;
  overflow-y: auto;
  ${scrollbarStyles}
`;

export const HorizontalScroll = styled.div`
  width: 100%;
  overflow-x: auto;
`;

export const LicenseItem = styled.div`
  width: 100%;
`;

export const LicenseHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
`;

// Use base components from common/styled with dashboard-specific variants
export const StatValue = BaseStatValue;

export const InlineLink = styled(RouterLink)`
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};

  &:hover {
  }
`;

export const QueueBadgeRow = styled(FlexColumn)``;

export const QueueBadge = styled(RediaccBadge)<{
  $variant?: 'error' | 'warning' | 'info' | 'default';
}>`
  .ant-scroll-number {
  }
`;

export const TimelineWrapper = styled(Timeline)`
  width: 100%;
`;

const { Item: AntListItem } = RediaccList;

export const BorderlessList = styled(RediaccList)`
  width: 100%;

  .ant-list-item {
  }
`;

export const BorderlessListItem = styled(AntListItem)`
  && {
  }
`;

export const AuditMeta = styled(RediaccText).attrs({ size: 'sm', color: 'secondary' })``;

export const SectionFooter = styled(FlexRow).attrs({ $justify: 'space-between' })`
  width: 100%;
`;

export const PlanCountBadge = styled(RediaccBadge)`
  .ant-scroll-number {
  }
`;

export const QuantityBadge = styled(RediaccBadge)`
  .ant-scroll-number {
  }
`;

// Icon color variant types for themed icons
type IconColorVariant = keyof Pick<
  StyledTheme['colors'],
  'success' | 'error' | 'warning' | 'info' | 'primary' | 'textSecondary'
>;

export const ActionIcon = styled.span<{ $color: IconColorVariant }>`
`;

export const ErrorText = styled(RediaccText)`
  && {
  }
`;

export const DaysRemainingText = styled(RediaccText)<{ $critical?: boolean }>`
  && {
  }
`;

export const SectionTitle = styled(RediaccText)`
`;

type StatusIconVariant = 'warning' | 'success' | 'secondary';

export const StatusIcon = styled.span<{ $variant?: StatusIconVariant }>`
`;
