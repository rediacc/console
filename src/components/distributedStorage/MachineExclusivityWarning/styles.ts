import styled from 'styled-components'
import { Alert, Typography } from 'antd'

export const WarningAlert = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    background-color: ${({ theme }) => theme.colors.bgWarning};
    border: 1px solid ${({ theme }) => theme.colors.warning};
  }
`

export const InlineWarningAlert = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const MessageText = styled.span`
  color: ${({ theme }) => theme.colors.textPrimary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`

export const DescriptionWrapper = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const RuleList = styled.ul`
  margin: ${({ theme }) => theme.spacing.SM}px 0 0;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
  color: ${({ theme }) => theme.colors.textPrimary};

  li {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const StyledText = styled(Typography.Text)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`
