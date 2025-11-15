import styled, { css } from 'styled-components'
import { Card, Input, Typography, Tag, Button, Alert, InputNumber, Select } from 'antd'
import { BaseModal } from '@/styles/primitives'
import type { StyledTheme } from '@/styles/styledTheme'
import { InfoCircleOutlined, QuestionCircleOutlined } from '@/utils/optimizedIcons'

const { Text } = Typography

const resolvePriorityTokens = (priority: number, theme: StyledTheme) => {
  switch (priority) {
    case 1:
      return {
        color: theme.colors.error,
        bg: theme.colors.bgError,
        border: theme.colors.error,
      }
    case 2:
      return {
        color: theme.colors.warning,
        bg: theme.colors.bgWarning,
        border: theme.colors.warning,
      }
    case 3:
      return {
        color: theme.colors.info,
        bg: theme.colors.bgInfo,
        border: theme.colors.info,
      }
    case 4:
      return {
        color: theme.colors.primary,
        bg: theme.colors.primaryBg,
        border: theme.colors.primary,
      }
    default:
      return {
        color: theme.colors.success,
        bg: theme.colors.bgSuccess,
        border: theme.colors.success,
      }
  }
}

const resolveLineageTokens = (
  variant: 'parent' | 'source' | 'destination',
  theme: StyledTheme
) => {
  switch (variant) {
    case 'parent':
      return {
        color: theme.colors.info,
        bg: theme.colors.bgInfo,
        border: theme.colors.info,
      }
    case 'source':
      return {
        color: theme.colors.success,
        bg: theme.colors.bgSuccess,
        border: theme.colors.success,
      }
    default:
      return {
        color: theme.colors.primary,
        bg: theme.colors.primaryBg,
        border: theme.colors.primary,
      }
  }
}

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
    padding-top: ${({ theme }) => theme.spacing.LG}px;
  }
`

const CardBase = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`

export const FunctionListCard = styled(CardBase)``

export const ConfigCard = styled(CardBase)``

export const SearchInput = styled(Input.Search)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const FunctionList = styled.div`
  max-height: 400px;
  overflow: auto;
  padding: ${({ theme }) => theme.spacing.XS}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`

export const CategorySection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const CategoryTitle = styled(Text)`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`

export const FunctionItemHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const FunctionOption = styled.button.attrs({ type: 'button' })<{
  $selected?: boolean
}>`
  width: 100%;
  border: ${({ theme, $selected }) =>
    $selected ? `2px solid ${theme.colors.primary}` : `1px solid ${theme.colors.borderSecondary}`};
  background-color: ${({ theme, $selected }) =>
    $selected ? theme.colors.primaryBg : theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  transition: ${({ theme }) => theme.transitions.HOVER};
  text-align: left;
  font: inherit;
  color: inherit;

  &:hover {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: ${({ theme }) => theme.shadows.SM};
  }

  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.primary};
    outline-offset: 2px;
  }
`

export const QuickTaskTag = styled(Tag)`
  && {
    margin-left: ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border: 1px solid ${({ theme }) => theme.colors.warning};
    background-color: ${({ theme }) => theme.colors.bgWarning};
    color: ${({ theme }) => theme.colors.warning};
    line-height: 1.2;
  }
`

export const FunctionDescriptionText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const ContentStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const PushAlertsRow = styled.div<{ $hasWarning: boolean }>`
  display: grid;
  grid-template-columns: ${({ $hasWarning }) => ($hasWarning ? '1fr 0.8fr' : '1fr')};
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;

  @media (max-width: 992px) {
    grid-template-columns: 1fr;
  }
`

export const PushAlertCard = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border-width: 1px;
    height: 100%;
  }

  ${({ theme, type }) =>
    type === 'info'
      ? css`
          border-color: ${theme.colors.info};
        `
      : css`
          border-color: ${theme.colors.warning};
        `}
`

export const AlertBodyText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const AlertLinkWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const AlertLink = styled.a`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.primary};

  &:hover {
    color: ${({ theme }) => theme.colors.primaryHover};
  }
`

export const LineageTag = styled(Tag).attrs<{ $variant: 'parent' | 'source' | 'destination' }>({
  bordered: true,
})<{ $variant: 'parent' | 'source' | 'destination' }>`
  && {
    ${({ theme, $variant }) => {
      const tokens = resolveLineageTokens($variant, theme)
      return css`
        border-color: ${tokens.border};
        color: ${tokens.color};
        background-color: ${tokens.bg};
      `
    }}
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const LineageSeparator = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const HelpTooltipIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  cursor: help;
`

export const PriorityHelpIcon = styled(QuestionCircleOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
  cursor: pointer;
`

export const SizeInputGroup = styled.div`
  display: flex;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const SizeValueInput = styled(InputNumber)`
  && {
    flex: 1 1 65%;
  }
`

export const SizeUnitSelect = styled(Select)`
  && {
    flex: 0 0 35%;
  }
`

export const CheckboxGroupStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
  width: 100%;
`

export const AdditionalOptionsInput = styled(Input)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const PriorityPopoverContent = styled.div`
  max-width: 400px;
`

export const PriorityPopoverHeader = styled(Text)`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`

export const PriorityLegendRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`

export const PriorityLegendTag = styled(Tag)<{ $level: number }>`
  && {
    ${({ theme, $level }) => {
      const tokens = resolvePriorityTokens($level, theme)
      return css`
        background-color: ${tokens.bg};
        color: ${tokens.color};
        border-color: ${tokens.border};
      `
    }}
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const PriorityLegendText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const PriorityTagWrapper = styled.div`
  text-align: center;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const PriorityStatusTag = styled(Tag)<{ $priority: number }>`
  && {
    ${({ theme, $priority }) => {
      const tokens = resolvePriorityTokens($priority, theme)
      return css`
        background-color: ${tokens.bg};
        color: ${tokens.color};
        border-color: ${tokens.border};
      `
    }}
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const PriorityAlert = styled(Alert)`
  && {
    margin-top: ${({ theme }) => theme.spacing.LG}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const PriorityAlertNote = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`

export const PriorityAlertDetail = styled.div`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
  font-style: italic;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const PrimarySubmitButton = styled(Button)`
  && {
    background-color: ${({ theme }) => theme.colors.primary};
    border-color: ${({ theme }) => theme.colors.primary};
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;

    &:hover,
    &:focus {
      background-color: ${({ theme }) => theme.colors.primaryHover};
      border-color: ${({ theme }) => theme.colors.primaryHover};
    }
  }
`
