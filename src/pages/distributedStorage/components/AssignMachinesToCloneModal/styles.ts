import styled from 'styled-components'
import { Button, Select, Typography } from 'antd'
import {
  BaseModal,
  BaseTable,
  ModalContentStack,
  ModalTitleRow,
  PaddedEmpty,
  PillTag,
  FormLabel,
  AlertCard,
} from '@/styles/primitives'
import { ModalSize } from '@/types/modal'

const { Text } = Typography

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} assign-clone-machines-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const TitleStack = styled(ModalTitleRow)``

export const CloneTag = styled(PillTag).attrs({
  $variant: 'warning',
  $size: 'MD',
  $borderless: true,
})``

const TabStack = styled(ModalContentStack)`
  width: 100%;
`

export const AssignTabContainer = TabStack
export const ManageTabContainer = TabStack

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``
export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })``

export const FieldGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const FieldLabel = FormLabel

export const StyledSelect = styled(Select)`
  && {
    width: 100%;

    .ant-select-selector {
      min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_SM}px;
      border-radius: ${({ theme }) => theme.borderRadius.MD}px !important;
      background-color: ${({ theme }) => theme.colors.inputBg};
      border-color: ${({ theme }) => theme.colors.inputBorder} !important;
      transition: ${({ theme }) => theme.transitions.DEFAULT};
      padding: 0 ${({ theme }) => theme.spacing.SM}px;
    }

    &.ant-select-focused .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.primary} !important;
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    }
  }
`

export const EmptyState = styled(PaddedEmpty)`
  margin-top: ${({ theme }) => theme.spacing.XL}px;
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
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const BridgeTag = styled(PillTag).attrs({
  $variant: 'success',
  $size: 'SM',
  $borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`

export const SelectionCount = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const FooterButton = styled(Button)`
  min-width: 120px;
`
