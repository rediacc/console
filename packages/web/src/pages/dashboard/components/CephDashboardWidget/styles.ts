import styled from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import { RediaccCard, RediaccList, RediaccText } from '@/components/ui';
import { FlexColumn, FlexRow } from '@/styles/primitives';

export const WidgetCard = styled(RediaccCard)`
`;

export const TitleIcon = styled.span`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const TitleText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XL}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

// Use FlexColumn from primitives
export const WidgetBody = styled(FlexColumn).attrs({})`
`;

export const AssignmentCard = styled(RediaccCard)<{ $borderColor: string }>`
  text-align: center;
`;

// Use FlexColumn from primitives
export const AssignmentStack = styled(FlexColumn).attrs({ $align: 'center' })``;

export const AssignmentIcon = styled.div<{ $color: string }>`
  font-size: ${({ theme }) => theme.dimensions.ICON_XL}px;
`;

export const PercentageText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

// Use FlexColumn from primitives
export const SummaryPanel = styled(FlexColumn).attrs({})`
`;

// Use FlexColumn from primitives
export const TeamSection = styled(FlexColumn).attrs({})``;

// Use FlexRow from primitives
export const TeamHeader = styled(FlexRow).attrs({})``;

export const TeamListStyled = styled(RediaccList)`
  .ant-list-items {
    display: flex;
    flex-direction: column;
  }
`;

export const TeamListItem = styled(RediaccList.Item)`
  &.ant-list-item {
  }
`;

export const TeamListContent = styled.div`
  width: 100%;
`;

// Use FlexRow from primitives
export const TeamListHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
`;

export const TeamName = styled(RediaccText).attrs({ weight: 'medium' })``;

export const TeamMeta = styled(RediaccText).attrs({ size: 'sm', color: 'secondary' })``;

// Use ActionGroup from common/styled (flex-wrap with SM gap)
export const TeamTagGroup = ActionGroup;
