import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccBadge, RediaccButton, RediaccCard, RediaccTag } from '@/components/ui';
import type { TagPreset, TagVariant } from '@/components/ui/Tag';
import { FlexColumn } from '@/styles/primitives';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export type { TagVariant, TagPreset };

export const MachineTableWrapper = styled(FlexColumn).attrs({})`
  height: 100%;

  /* Custom selection state - RediaccTable handles hover via interactive prop */
  .machine-table-row--selected td {
  }
`;

export const TableContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

export const BulkActionsBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

export const BulkActionsSummary = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const ViewToggleContainer = styled.div`
`;

export const ViewToggleButton = styled(RediaccButton)`
  && {
    min-width: 42px;
  }
`;

export const ViewToggleDivider = styled.span`
  width: 1px;
  height: ${({ theme }) => theme.spacing.LG}px;
`;

export const GroupedCardStack = styled.div`
  display: flex;
  flex-direction: column;
`;

export const GroupCardContainer = styled(RediaccCard)<{ $isAlternate: boolean }>`
  && {
  }

  .ant-card-head {
  }

  .ant-card-body {
  }
`;

export const GroupCardHeader = styled(InlineStack)`
`;

export const GroupCardIndicator = styled.div<{ $color?: string }>`
  width: ${({ theme }) => theme.spacing.XS}px;
  height: ${DESIGN_TOKENS.DIMENSIONS.ICON_XL}px;
`;

export const GroupCardTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.BOLD};
`;

export const GroupCardCount = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const GroupCardRow = styled.div<{ $isStriped: boolean }>`
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;

  &:hover {
  }
`;

export const GroupRowContent = styled.div`
  display: flex;
  align-items: center;
`;

export const MachineNameIcon = styled(DesktopOutlined)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_MD}px;
`;

export const GroupRowIcon = styled(MachineNameIcon)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_LG}px;
`;

export const GroupRowInfo = styled.div`
  display: flex;
  flex-direction: column;
`;

export const GroupRowName = styled.span`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const GroupRowActionButton = styled(RediaccButton)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
  }
`;

export const StyledTag = styled(RediaccTag).attrs<{ $preset?: TagPreset; $variant?: TagPreset }>(
  ({ $preset, $variant }) => ({
    preset: $preset || $variant,
    borderless: true,
  })
)<{ $preset?: TagPreset; $variant?: TagPreset }>``;

export const GroupHeaderTag = styled(RediaccTag).attrs<{ $preset?: string; $variant?: string }>(
  ({ $preset, $variant }) => ({
    preset: ($preset || $variant) as TagPreset,
    borderless: true,
    size: 'md' as const,
  })
)<{ $preset?: string; $variant?: string }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.MD}px;
  }
`;

export const StyledBadge = styled(RediaccBadge)<{ $isPositive: boolean }>`
  && .ant-badge-count {
  }
`;

export const StyledRediaccEmpty = styled.div`
`;
