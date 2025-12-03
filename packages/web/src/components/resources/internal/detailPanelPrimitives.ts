import styled, { css } from 'styled-components'
import { Typography } from 'antd'

const { Text } = Typography

export const PanelWrapper = styled.div<{ $splitView?: boolean; $visible?: boolean }>`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  display: flex;
  flex-direction: column;
  ${({ $splitView, $visible }) =>
    $splitView
      ? css`
          width: 100%;
          height: 100%;
        `
      : css`
          position: fixed;
          top: 0;
          right: ${($visible ? 0 : -520)}px;
          bottom: 0;
          width: 520px;
          max-width: 100vw;
          box-shadow: -2px 0 8px rgba(0, 0, 0, 0.15);
          z-index: ${({ theme }) => theme.zIndex.MODAL};
          transition: right ${({ theme }) => theme.transitions.NORMAL};
        `}
`

export const StickyHeader = styled.div`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.XL}px`};
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  position: sticky;
  top: 0;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  z-index: 10;
`

export const ContentWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.XL}px;
`

export const InlineField = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const LabelText = styled(Text)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  && {
    margin: 0;
  }
`

export const ValueText = styled(Text)`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
  && {
    margin: 0;
  }
`

export const StrongValueText = styled(ValueText)`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`

export const MonospaceValue = styled(ValueText)`
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`
