import styled from 'styled-components';
import { Card, Statistic, List, Typography } from 'antd';

const { Text } = Typography;

export const WidgetCard = styled(Card)`
  border: 1px solid var(--color-border-secondary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

export const HeaderContent = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
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

export const Subtitle = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const WidgetBody = styled.div`
  width: 100%;
  padding: ${({ theme }) => theme.spacing.MD}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const AssignmentCard = styled(Card)<{ $borderColor: string }>`
  text-align: center;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
  background: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ $borderColor }) => $borderColor};
`;

export const AssignmentStack = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

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

export const SummaryPanel = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid var(--color-border-secondary);
  box-shadow: ${({ theme }) => theme.shadows.CARD};
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const SummaryTitle = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.H5}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const TeamSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const TeamHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const TeamListStyled = styled(List)`
  .ant-list-items {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const TeamListItem = styled(List.Item)`
  padding: ${({ theme }) => theme.spacing.SM}px !important;
  background: ${({ theme }) => theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  border: 1px solid var(--color-border-secondary);
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

export const TeamListContent = styled.div`
  width: 100%;
`;

export const TeamListHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
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

export const TeamTagGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;
