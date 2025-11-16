/**
 * Utility components
 * 
 * General-purpose layout utilities:
 * - IconWrapper: Icon container with sizing
 * - RightAlign, CenteredState, CenteredBlock, ErrorWrapper
 * - PaddedEmpty: Ant Design Empty with padding
 * - RegionsSection: Special section for infrastructure page
 */

import styled, { type DefaultTheme } from 'styled-components'
import { Empty } from 'antd'

type IconSize = 'sm' | 'md' | 'lg'

const getIconSize = (size: IconSize, theme: DefaultTheme) => {
  switch (size) {
    case 'sm':
      return `${theme.dimensions.ICON_SM}px`
    case 'lg':
      return `${theme.dimensions.ICON_LG}px`
    default:
      return `${theme.dimensions.ICON_MD}px`
  }
}

/**
 * IconWrapper - Wrapper for icons with consistent sizing
 */
export const IconWrapper = styled.span<{ $size?: IconSize; $tone?: 'primary' | 'inherit' }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size = 'md' }) => getIconSize($size, theme)};
  color: ${({ theme, $tone = 'primary' }) => ($tone === 'primary' ? theme.colors.primary : 'currentColor')};
`

export const RightAlign = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
  text-align: right;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`

export const CenteredState = styled.div`
  width: 100%;
  text-align: center;
  padding: ${({ theme }) => theme.spacing['6']}px 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const CenteredBlock = styled.div`
  text-align: center;
`

export const ErrorWrapper = styled.div`
  max-width: 480px;
  margin: 0 auto;
  width: 100%;
`

export const PaddedEmpty = styled(Empty)`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
`

export const RegionsSection = styled.section`
  margin-top: ${({ theme }) => theme.spacing['6']}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`
