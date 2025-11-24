import styled from 'styled-components'
import { Alert, Select, Typography } from 'antd'
import { BaseModal } from '@/styles/primitives'
import { ModalSize } from '@/types/modal'
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons'

const { Text } = Typography

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} image-machine-reassignment-modal`,
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
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const TitleIcon = styled(FileImageOutlined)`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const ContentStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const FieldRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const FieldLabel = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const FieldValue = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

const BaseAlert = styled(Alert)`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`

export const InfoAlert = BaseAlert
export const WarningAlert = BaseAlert

export const MachineIcon = styled(CloudServerOutlined)`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const StyledSelect = styled(Select)`
  && {
    width: 100%;

    .ant-select-selector {
      min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
      border-radius: ${({ theme }) => theme.borderRadius.MD}px !important;
      border-color: ${({ theme }) => theme.colors.inputBorder} !important;
      background-color: ${({ theme }) => theme.colors.inputBg};
      padding: 0 ${({ theme }) => theme.spacing.SM}px;
      transition: ${({ theme }) => theme.transitions.DEFAULT};
    }

    &.ant-select-focused .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.primary} !important;
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    }
  }
`

export const SelectLabel = styled(Text)`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const SelectOptionText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const DisabledOptionText = styled(SelectOptionText)`
  opacity: 0.6;
`

export const HelperText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.MD}px 0;
`
