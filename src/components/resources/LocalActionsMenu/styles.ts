import styled from 'styled-components'
import { Button } from 'antd'
import type { StyledTheme } from '@/styles/styledTheme'

export const TriggerButton = styled(Button).attrs({
  size: 'small',
})`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`

type IconSize = 'sm' | 'md'

const resolveIconSize = (size: IconSize, theme: StyledTheme) => {
  switch (size) {
    case 'md':
      return `${theme.fontSize.LG}px`
    case 'sm':
    default:
      return `${theme.fontSize.MD}px`
  }
}

export const IconWrapper = styled.span<{ $size?: IconSize }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size = 'sm' }) => resolveIconSize($size, theme)};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const MenuLabel = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`
