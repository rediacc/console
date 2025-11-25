import styled from 'styled-components'
import { Button, Card } from 'antd'
import { CloudServerOutlined, DatabaseOutlined } from '@/utils/optimizedIcons'
import {
  TableContainer as BaseTableContainer,
  TableCellContent,
  TableCellText,
  ExpandIcon as BaseExpandIcon,
  PillTag,
  StyledIcon,
} from '@/styles/primitives'

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

export const CardIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``

export const CardTitle = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ClusterTag = styled(PillTag).attrs({
  $variant: 'team',
  $size: 'SM',
})``

export const TableWrapper = styled(BaseTableContainer)`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  .pool-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  .pool-row:hover {
    background: ${({ theme }) => theme.colors.bgHover};
  }
`

export const PoolNameCell = styled(TableCellContent)``

export const ExpandIcon = styled(BaseExpandIcon)<{ $expanded: boolean }>``

export const PoolIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: DatabaseOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``

export const PoolNameText = styled(TableCellText)``
