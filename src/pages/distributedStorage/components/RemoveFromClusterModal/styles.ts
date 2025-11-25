import styled from 'styled-components'
import { Typography } from 'antd'
import { BaseModal, BaseTable, ModalTitleRow, PillTag, AlertCard } from '@/styles/primitives'
import { WarningOutlined } from '@/utils/optimizedIcons'
import { ModalSize } from '@/types/modal'

const { Text } = Typography

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} remove-from-cluster-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const TitleStack = styled(ModalTitleRow)``

export const DangerIcon = styled(WarningOutlined)`
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.XL}px;
`

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``

export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const MachineNameRow = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const MachineNameText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const ClusterTag = styled(PillTag).attrs({
  $variant: 'cluster',
  $size: 'SM',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`

export const MutedText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`
