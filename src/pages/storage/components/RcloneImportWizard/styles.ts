import styled from 'styled-components'
import { Modal, Alert, Typography } from 'antd'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import { LoadingState as BaseLoadingState } from '@/styles/primitives'

const { Title, Text } = Typography

export const WizardModal = styled(Modal).attrs({
  width: DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_XL,
})`
  && {
    max-width: calc(100vw - ${DESIGN_TOKENS.SPACING['4']}px);
  }

  .ant-modal-content {
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    box-shadow: ${({ theme }) => theme.shadows.MODAL};
    border: none;
    background-color: var(--color-bg-primary);
  }

  .ant-modal-header {
    border-bottom: 1px solid var(--color-border-secondary);
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: var(--color-bg-primary);
  }

  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.XL}px;
  }

  .ant-modal-footer {
    border-top: 1px solid var(--color-border-secondary);
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: var(--color-bg-primary);
  }
`

export const UploadStepWrapper = styled.div`
  padding: ${({ theme }) => `${theme.spacing.LG}px 0`};
`

export const InstructionsAlert = styled(Alert)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const StandardAlert = styled(Alert)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const ErrorAlert = styled(Alert)`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`

export const StepsContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const LoadingState = styled(BaseLoadingState).attrs({
  $paddingY: 'XXL',
})``

export const LoadingTitle = styled(Title)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const StatusMessage = styled(Text)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
    color: var(--color-text-secondary);
  }
`
