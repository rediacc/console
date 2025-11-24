import styled from 'styled-components'
import { Form, Tabs, Typography } from 'antd'
import { BaseModal } from '@/styles/primitives'
import { ModalSize } from '@/types/modal'

const { Text, Paragraph } = Typography

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} local-command-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const Description = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    display: block;
  }
`

export const SettingsForm = styled(Form)`
  && {
    margin-bottom: 0;

    .ant-form-item {
      margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    }
  }
`

export const CheckboxHelper = styled(Text)`
  && {
    margin-left: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const TabsWrapper = styled(Tabs)`
  && {
    .ant-tabs-nav {
      margin-bottom: ${({ theme }) => theme.spacing.MD}px;
    }
  }
`

export const CommandPreview = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.LG}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.XL}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`

export const PreviewHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const PreviewTitle = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const PreviewError = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const PreviewErrorText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.error};
  }
`

export const PreviewHelper = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`

export const CommandParagraph = styled(Paragraph)`
  && {
    margin: 0;
    font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    white-space: pre-wrap;
  }
`

export const PreviewMetaRow = styled.div`
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const PreviewMetaText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const ActionsRow = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.spacing.SM}px;
`
