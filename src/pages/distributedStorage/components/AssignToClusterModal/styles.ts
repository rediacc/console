import styled from 'styled-components'
import { Select, Typography } from 'antd'
import {
  BaseModal,
  BaseTable,
  ModalContentStack,
  ModalTitleRow,
  PillTag,
  HelperText as PrimitiveHelperText,
  FormLabel,
  AlertCard,
} from '@/styles/primitives'
import { ModalSize } from '@/types/modal'

const { Text } = Typography

export const StyledModal = styled(BaseModal).attrs<{ $size: ModalSize }>(({ $size }) => ({
  className: `${$size} assign-to-cluster-modal`,
}))<{ $size: ModalSize }>`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const TitleStack = styled(ModalTitleRow)``

export const ContentStack = styled(ModalContentStack)`
  width: 100%;
`

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``

export const ClusterAlert = styled(AlertCard).attrs({ $variant: 'warning' })`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const MachineDetailsSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const DetailRow = styled.div`
  display: inline-flex;
  gap: ${({ theme }) => theme.spacing.XS}px;
  align-items: baseline;
`

export const DetailLabel = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const DetailValue = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

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
      min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
      border-radius: ${({ theme }) => theme.borderRadius.MD}px !important;
      background-color: ${({ theme }) => theme.colors.inputBg};
      border-color: ${({ theme }) => theme.colors.inputBorder} !important;
      padding: 0 ${({ theme }) => theme.spacing.SM}px;
      transition: ${({ theme }) => theme.transitions.DEFAULT};
    }

    &.ant-select-focused .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.primary} !important;
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    }
  }
`

export const HelperText = PrimitiveHelperText

export const LoadingWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
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

export const TeamTag = styled(PillTag).attrs({
  $variant: 'success',
  $size: 'SM',
  $borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`

export const AssignmentTag = styled(PillTag).attrs({
  $size: 'SM',
})<{ $variant: 'cluster' | 'available' }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`
