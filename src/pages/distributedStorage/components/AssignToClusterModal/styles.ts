import styled from 'styled-components'
import { Alert, Select, Tag, Typography } from 'antd'
import { BaseModal, BaseTable } from '@/styles/primitives'
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

export const ContentStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
  width: 100%;
`

const BaseAlert = styled(Alert)`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  padding: ${({ theme }) => theme.spacing.MD}px ${({ theme }) => theme.spacing.LG}px;
`

export const InfoAlert = BaseAlert

export const ClusterAlert = styled(BaseAlert)`
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

export const HelperText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

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

export const TeamTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({ theme }) => theme.colors.bgSuccess};
    color: ${({ theme }) => theme.colors.success};
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`

export const AssignmentTag = styled(Tag)<{ $variant: 'cluster' | 'available' }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
    border-color: ${({ theme, $variant }) =>
      $variant === 'cluster' ? theme.colors.primary : theme.colors.success};
    color: ${({ theme, $variant }) => ($variant === 'cluster' ? theme.colors.primary : theme.colors.success)};
    background-color: ${({ theme, $variant }) =>
      $variant === 'cluster' ? theme.colors.primaryBg : theme.colors.bgSuccess};
  }
`
