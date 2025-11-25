import styled from 'styled-components'
import { Card, Statistic } from 'antd'
import { ReloadOutlined } from '@/utils/optimizedIcons'
import { StyledIcon } from '@/styles/primitives'

export const SummaryCard = styled(Card)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const LoadingCard = styled(Card)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const LoadingContent = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
`

export const RefreshButton = styled.button`
  border: none;
  background: transparent;
  padding: ${({ theme }) => theme.spacing.XS}px;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color ${({ theme }) => theme.transitions.FAST},
    background ${({ theme }) => theme.transitions.FAST};

  &:hover {
    color: var(--color-primary);
    background: var(--color-fill-tertiary);
  }
`

export const RefreshIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: ReloadOutlined,
  $size: theme.spacing.MD,
}))``

export const StatCard = styled(Card)`
  text-align: center;
`

export const SummaryStatistic = styled(Statistic)<{ $accent?: string }>`
  && .ant-statistic-content-value {
    color: ${({ $accent }) => $accent || 'var(--color-text-primary)'};
  }
`

export const PercentageSuffix = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`
