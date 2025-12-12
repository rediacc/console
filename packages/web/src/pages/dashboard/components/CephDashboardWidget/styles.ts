import styled from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import { RediaccCard, RediaccList, RediaccText } from '@/components/ui';
import { FlexColumn, FlexRow } from '@/styles/primitives';

export const WidgetCard = styled(RediaccCard)`
  border: 1px solid var(--color-border-secondary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

export const TitleIcon = styled.span`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`;

export const TitleText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.H4}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

// Use FlexColumn from primitives
export const WidgetBody = styled(FlexColumn).attrs({ $gap: 'LG' })`
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const AssignmentCard = styled(RediaccCard)<{ $borderColor: string }>`
  text-align: center;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
  background: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ $borderColor }) => $borderColor};
`;

// Use FlexColumn from primitives
export const AssignmentStack = styled(FlexColumn).attrs({ $gap: 'XS', $align: 'center' })``;

export const AssignmentIcon = styled.div<{ $color: string }>`
  font-size: ${({ theme }) => theme.dimensions.ICON_XL}px;
  color: ${({ $color }) => $color};
`;

export const PercentageText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

// Use FlexColumn from primitives
export const SummaryPanel = styled(FlexColumn).attrs({ $gap: 'MD' })`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid var(--color-border-secondary);
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

// Use FlexColumn from primitives
export const TeamSection = styled(FlexColumn).attrs({ $gap: 'SM' })``;

// Use FlexRow from primitives
export const TeamHeader = styled(FlexRow).attrs({ $gap: 'SM' })``;

export const TeamListStyled = styled(RediaccList)`
  .ant-list-items {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const TeamListItem = styled(RediaccList.Item)`
  &.ant-list-item {
    padding: ${({ theme }) => theme.spacing.SM}px;
    background: ${({ theme }) => theme.colors.bgPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border: 1px solid var(--color-border-secondary);
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const TeamListContent = styled.div`
  width: 100%;
`;

// Use FlexRow from primitives
export const TeamListHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const TeamName = styled(RediaccText).attrs({ weight: 'medium' })``;

export const TeamMeta = styled(RediaccText).attrs({ size: 'sm', color: 'secondary' })``;

// Use ActionGroup from common/styled (flex-wrap with SM gap)
export const TeamTagGroup = ActionGroup;
