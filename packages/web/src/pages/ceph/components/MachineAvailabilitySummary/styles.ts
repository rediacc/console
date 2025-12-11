import { Statistic } from 'antd';
import styled from 'styled-components';
import { RediaccCard } from '@/components/ui';
import { FlexRow, StyledIcon } from '@/styles/primitives';
import { ReloadOutlined } from '@/utils/optimizedIcons';

export const LoadingContent = styled(FlexRow).attrs({ $justify: 'center' })`
  padding: ${({ theme }) => theme.spacing.LG}px 0;
`;

export const RefreshButton = styled.button`
  border: none;
  background: transparent;
  padding: ${({ theme }) => theme.spacing.XS}px;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textSecondary};
  cursor: pointer;
  transition: color ${({ theme }) => theme.transitions.FAST},
    background ${({ theme }) => theme.transitions.FAST};

  &:hover {
    color: ${({ theme }) => theme.colors.primary};
    background: ${({ theme }) => theme.colors.bgHover};
  }
`;

export const RefreshIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: ReloadOutlined,
  $size: theme.spacing.MD,
}))``;

export const StatCard = styled(RediaccCard)`
  text-align: center;
`;

export const SummaryStatistic = styled(Statistic)<{ $accent?: string }>`
  && .ant-statistic-content-value {
    color: ${({ $accent, theme }) => $accent || theme.colors.textPrimary};
  }
`;

export const PercentageSuffix = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const StyledRediaccCard = styled(RediaccCard)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;
