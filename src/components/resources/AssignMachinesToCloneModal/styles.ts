import styled from 'styled-components'
import { Alert, Button, Empty, Select, Tag, Typography } from 'antd'
import { BaseModal, BaseTable } from '@/styles/primitives'
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

  .ant-modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const TitleStack = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const CloneTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({ theme }) => theme.colors.bgWarning};
    color: ${({ theme }) => theme.colors.warning};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

const TabStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
  width: 100%;
`

export const AssignTabContainer = TabStack
export const ManageTabContainer = TabStack

const BaseAlert = styled(Alert)`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`

export const InfoAlert = BaseAlert
export const WarningAlert = BaseAlert

export const FieldGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const FieldLabel = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

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

export const EmptyState = styled(Empty)`
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

export const BridgeTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({ theme }) => theme.colors.bgSuccess};
    color: ${({ theme }) => theme.colors.success};
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
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
