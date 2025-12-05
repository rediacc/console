import styled from 'styled-components';
import { Card, Statistic, List, Typography } from 'antd';
import { FlexColumn, FlexRow } from '@/styles/primitives';
import { ActionGroup } from '@/components/common/styled';

const { Text } = Typography;

export const WidgetCard = styled(Card)`
  border: 1px solid var(--color-border-secondary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

// Use InlineStack from common/styled
export { InlineStack as HeaderContent } from '@/components/common/styled';

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

export const Subtitle = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

// Use FlexColumn from primitives
export const WidgetBody = styled(FlexColumn).attrs({ $gap: 'LG' })`
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const AssignmentCard = styled(Card)<{ $borderColor: string }>`
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

export const AssignmentStatistic = styled(Statistic)<{ $color: string }>`
  && .ant-statistic-content-value {
    color: ${({ $color }) => $color};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
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

export const SummaryTitle = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.H5}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

// Use FlexColumn from primitives
export const TeamSection = styled(FlexColumn).attrs({ $gap: 'SM' })``;

// Use FlexRow from primitives
export const TeamHeader = styled(FlexRow).attrs({ $gap: 'SM' })``;

export const TeamListStyled = styled(List)`
  .ant-list-items {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const TeamListItem = styled(List.Item)`
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

export const TeamName = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const TeamMeta = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

// Use ActionGroup from common/styled (flex-wrap with SM gap)
export const TeamTagGroup = ActionGroup;
