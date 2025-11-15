import styled, { css } from 'styled-components'
import { Alert, Button, Card, Divider, Typography } from 'antd'
import type { StyledTheme } from '@/styles/styledTheme'

const { Text } = Typography

type IconSize = 'sm' | 'md' | 'lg'
type IconTone = 'primary' | 'muted' | 'info' | 'warning'

const resolveIconSize = (size: IconSize, theme: StyledTheme) => {
  switch (size) {
    case 'sm':
      return `${theme.fontSize.SM}px`
    case 'lg':
      return `${theme.fontSize.XL}px`
    case 'md':
    default:
      return `${theme.fontSize.LG}px`
  }
}

const resolveIconColor = (tone: IconTone, theme: StyledTheme) => {
  switch (tone) {
    case 'muted':
      return theme.colors.textSecondary
    case 'info':
      return theme.colors.info
    case 'warning':
      return theme.colors.warning
    case 'primary':
    default:
      return theme.colors.primary
  }
}

export const LoadingState = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.LG}px;
`

export const SectionDivider = styled(Divider)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
    border-color: ${({ theme }) => theme.colors.borderSecondary};
  }
`

export const DividerContent = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const SectionTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const IconWrapper = styled.span<{ $size?: IconSize; $tone?: IconTone }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size = 'md' }) => resolveIconSize($size, theme)};
  color: ${({ theme, $tone = 'primary' }) => resolveIconColor($tone, theme)};
`

export const SectionCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const ContentStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const AssignmentLabel = styled(Text)`
  && {
    display: block;
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const AlertWrapper = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const AlertMessage = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ActionsRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

const actionButtonStyles = css`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const ActionButton = styled(Button).attrs({
  size: 'small',
})`
  ${actionButtonStyles}
`

export const ButtonLabel = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`
