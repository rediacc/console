import styled from 'styled-components'
import { Card, Empty, Button, Tag } from 'antd'
import {
  CloudServerOutlined,
  DatabaseOutlined,
  RightOutlined,
} from '@/utils/optimizedIcons'

export const EmptyStateWrapper = styled(Empty)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XL}px;
  }
`

export const CreatePoolButton = styled(Button)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const ClusterCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const CardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const CardIcon = styled(CloudServerOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const CardTitle = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ClusterTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.success};
    color: ${({ theme }) => theme.colors.success};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const TableWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};

  .pool-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  .pool-row:hover {
    background: ${({ theme }) => theme.colors.bgHover};
  }
`

export const PoolNameCell = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ExpandIcon = styled(RightOutlined)<{ $expanded: boolean }>`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
  color: ${({ theme }) => theme.colors.textTertiary};
  transition: transform ${({ theme }) => theme.transitions.FAST};
  transform: ${({ $expanded }) =>
    $expanded ? 'rotate(90deg)' : 'rotate(0deg)'};
`

export const PoolIcon = styled(DatabaseOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const PoolNameText = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const VersionTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.info};
    color: ${({ theme }) => theme.colors.info};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const ActionButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`

export const ActionsContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`
