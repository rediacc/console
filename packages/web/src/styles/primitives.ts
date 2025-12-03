import styled, { css } from 'styled-components'
import {
  Card,
  Button,
  Table,
  Typography,
  Modal,
  Tag,
  Select,
  DatePicker,
  Input,
  InputNumber,
  Checkbox,
  Space,
  Badge,
  Empty,
  Alert,
} from 'antd'
import type { StyledTheme } from '@/styles/styledTheme'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import { RightOutlined } from '@/utils/optimizedIcons'

const { Title, Text } = Typography

export type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'processing'
export type TagVariant =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'neutral'
  | 'team'
  | 'cluster'
  | 'vault'
  | 'machine'
  | 'bridge'
  | 'available'
  | 'processing'
export type TagSize = 'SM' | 'MD'
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link'
export type ButtonSize = 'SM' | 'MD' | 'LG'
export type IconSize = 'SM' | 'MD' | 'LG' | 'XL' | 'XXL' | 'XXXL'
type IconSizeValue = IconSize | number

type SpacingScale = StyledTheme['spacing']
type SpacingToken = keyof SpacingScale
type SpacingValue = SpacingToken | number

const resolveSpacingValue = (
  theme: StyledTheme,
  value?: SpacingValue,
  fallback: SpacingToken = 'MD',
) => {
  if (typeof value === 'number') {
    return value
  }
  const token = (value || fallback) as SpacingToken
  return theme.spacing[token]
}

const resolveStatusTokens = (variant: StatusVariant = 'info', theme: StyledTheme) => {
  switch (variant) {
    case 'success':
      return {
        bg: theme.colors.bgSuccess,
        color: theme.colors.success,
        border: theme.colors.success,
      }
    case 'warning':
      return {
        bg: theme.colors.bgWarning,
        color: theme.colors.warning,
        border: theme.colors.warning,
      }
    case 'error':
      return {
        bg: theme.colors.bgError,
        color: theme.colors.error,
        border: theme.colors.error,
      }
    case 'processing':
      return {
        bg: theme.colors.primaryBg,
        color: theme.colors.primary,
        border: theme.colors.primary,
      }
    case 'neutral':
      return {
        bg: theme.colors.bgSecondary,
        color: theme.colors.textSecondary,
        border: theme.colors.borderSecondary,
      }
    case 'info':
    default:
      return {
        bg: theme.colors.bgInfo,
        color: theme.colors.info,
        border: theme.colors.info,
      }
  }
}

type TagTokenSet = { bg: string; color: string; border: string }

const resolveTagVariantTokens = (
  variant: TagVariant = 'neutral',
  theme: StyledTheme,
): TagTokenSet => {
  const map: Record<TagVariant, TagTokenSet> = {
    primary: {
      bg: theme.colors.primaryBg,
      color: theme.colors.primary,
      border: theme.colors.primary,
    },
    secondary: {
      bg: theme.colors.bgPrimary,
      color: theme.colors.secondary,
      border: theme.colors.secondary,
    },
    success: {
      bg: theme.colors.bgSuccess,
      color: theme.colors.success,
      border: theme.colors.success,
    },
    warning: {
      bg: theme.colors.bgWarning,
      color: theme.colors.warning,
      border: theme.colors.warning,
    },
    error: {
      bg: theme.colors.bgError,
      color: theme.colors.error,
      border: theme.colors.error,
    },
    info: {
      bg: theme.colors.bgInfo,
      color: theme.colors.info,
      border: theme.colors.info,
    },
    neutral: {
      bg: theme.colors.bgSecondary,
      color: theme.colors.textSecondary,
      border: theme.colors.borderSecondary,
    },
    team: {
      bg: theme.colors.bgPrimary,
      color: theme.colors.success,
      border: theme.colors.success,
    },
    cluster: {
      bg: theme.colors.primaryBg,
      color: theme.colors.primary,
      border: theme.colors.primary,
    },
    vault: {
      bg: theme.colors.bgSecondary,
      color: theme.colors.textPrimary,
      border: theme.colors.borderSecondary,
    },
    machine: {
      bg: theme.colors.bgPrimary,
      color: theme.colors.primary,
      border: theme.colors.borderSecondary,
    },
    bridge: {
      bg: theme.colors.bgPrimary,
      color: theme.colors.secondary,
      border: theme.colors.secondary,
    },
    available: {
      bg: theme.colors.bgSuccess,
      color: theme.colors.success,
      border: theme.colors.success,
    },
    processing: {
      bg: theme.colors.primaryBg,
      color: theme.colors.primary,
      border: theme.colors.primary,
    },
  }

  return map[variant] || map.neutral
}

const resolveTagPadding = (theme: StyledTheme, size: TagSize = 'SM') =>
  size === 'MD'
    ? `${theme.spacing.XS}px ${theme.spacing.SM}px`
    : `0 ${theme.spacing.XS}px`

const resolveTagRadius = (theme: StyledTheme, size: TagSize = 'SM') =>
  size === 'MD' ? theme.borderRadius.MD : theme.borderRadius.SM

const resolveTagFontSize = (theme: StyledTheme, size: TagSize = 'SM') =>
  size === 'MD' ? theme.fontSize.SM : theme.fontSize.CAPTION

type ButtonTokenSet = {
  bg: string
  color: string
  border: string
  hoverBg: string
  hoverColor: string
  hoverBorder: string
}

const resolveButtonVariantTokens = (
  variant: ButtonVariant = 'secondary',
  theme: StyledTheme,
): ButtonTokenSet => {
  switch (variant) {
    case 'primary':
      return {
        bg: theme.colors.primary,
        color: theme.colors.textInverse,
        border: theme.colors.primary,
        hoverBg: theme.colors.primaryHover,
        hoverColor: theme.colors.textInverse,
        hoverBorder: theme.colors.primaryHover,
      }
    case 'danger':
      return {
        bg: theme.colors.error,
        color: theme.colors.textInverse,
        border: theme.colors.error,
        hoverBg: theme.colors.error,
        hoverColor: theme.colors.textInverse,
        hoverBorder: theme.colors.error,
      }
    case 'ghost':
      return {
        bg: 'transparent',
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: theme.colors.borderSecondary,
      }
    case 'link':
      return {
        bg: 'transparent',
        color: theme.colors.primary,
        border: 'transparent',
        hoverBg: 'transparent',
        hoverColor: theme.colors.primaryHover,
        hoverBorder: 'transparent',
      }
    case 'secondary':
    default:
      return {
        bg: theme.colors.bgPrimary,
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: theme.colors.borderPrimary,
      }
  }
}

const resolveButtonHeight = (theme: StyledTheme, size: ButtonSize = 'MD') => {
  switch (size) {
    case 'SM':
      return theme.dimensions.CONTROL_HEIGHT_SM
    case 'LG':
      return theme.dimensions.CONTROL_HEIGHT_LG
    case 'MD':
    default:
      return theme.dimensions.CONTROL_HEIGHT
  }
}

const resolveIconSize = (theme: StyledTheme, size?: IconSizeValue) => {
  if (typeof size === 'number') {
    return size
  }
  const token = size || 'MD'
  switch (token) {
    case 'SM':
      return theme.dimensions.ICON_SM
    case 'LG':
      return theme.dimensions.ICON_LG
    case 'XL':
      return theme.dimensions.ICON_XL
    case 'XXL':
      return theme.dimensions.ICON_XXL
    case 'XXXL':
      return theme.dimensions.ICON_XXXL
    case 'MD':
    default:
      return theme.dimensions.ICON_MD
  }
}

type FontWeightScale = StyledTheme['fontWeight']
type FontWeightToken = keyof FontWeightScale

const resolveFontWeight = (theme: StyledTheme, value?: FontWeightToken | number) => {
  if (typeof value === 'number') {
    return value
  }
  const token = (value || 'SEMIBOLD') as FontWeightToken
  return theme.fontWeight[token]
}

type DimensionScale = StyledTheme['dimensions']
type DimensionToken = keyof DimensionScale

const resolveDimensionValue = (
  theme: StyledTheme,
  value?: DimensionToken | number,
  fallback: DimensionToken = 'ICON_SM',
) => {
  if (typeof value === 'number') {
    return value
  }
  const token = (value || fallback) as DimensionToken
  return theme.dimensions[token]
}

const fullWidthControlStyles = css`
  width: 100%;
`

const PasswordInput = Input.Password
const TextAreaInput = Input.TextArea

export const PageContainer = styled.div.attrs({ className: 'page-container' })`
  width: 100%;
`

export const PageCard = styled(Card).attrs({ className: 'page-card' })``

export const FilterCard = styled(Card).attrs({ className: 'page-card' })``

export const TableCard = styled(Card).attrs({ className: 'page-card' })`` 

export const SectionCard = styled(Card).attrs({ className: 'page-card' })``

// ============================================
// TABLE PRIMITIVES
// ============================================

export const ExpandIcon = styled(RightOutlined)<{
  $expanded?: boolean
  $visible?: boolean
  $color?: string
  $size?: DimensionToken | number
}>`
  font-size: ${({ theme, $size }) => `${resolveDimensionValue(theme, $size)}px`};
  color: ${({ theme, $color }) => $color || theme.colors.textTertiary};
  transition: transform ${({ theme }) => theme.transitions.FAST};
  transform: ${({ $expanded }) => ($expanded ? 'rotate(90deg)' : 'rotate(0deg)')};
  visibility: ${({ $visible = true }) => ($visible ? 'visible' : 'hidden')};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`

export const TableContainer = styled.div`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
`

export const TableCellContent = styled.span<{ $gap?: SpacingValue }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
`

export const TableCellText = styled.span<{
  $muted?: boolean
  $weight?: FontWeightToken | number
}>`
  font-weight: ${({ theme, $weight }) => resolveFontWeight(theme, $weight)};
  color: ${({ theme, $muted }) => ($muted ? theme.colors.textSecondary : theme.colors.textPrimary)};
`

// ============================================
// FILTER COMPONENTS
// ============================================

export const FiltersCard = styled(Card)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`

export const FiltersGrid = styled(Space).attrs({ size: 8, wrap: true })`
  width: 100%;
`

export const FilterSelect = styled(Select)<{ $minWidth?: number }>`
  min-width: ${({ $minWidth }) => ($minWidth ? `${$minWidth}px` : '150px')};
`

export const FilterRangePicker = styled(DatePicker.RangePicker)`
  min-width: 220px;
`

export const FilterInput = styled(Input)`
  min-width: 200px;
`

export const FilterCheckbox = styled(Checkbox)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`

// ============================================
// STATS COMPONENTS
// ============================================

export const StatsBar = styled(Space).attrs({ size: 12 })`
  align-items: center;
  flex-wrap: wrap;
`

export const StatItem = styled(Space).attrs({ size: 4 })`
  align-items: center;
`

export const StatLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const StatValue = styled(Text)<{ $color?: string }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ $color, theme }) => $color || theme.colors.textPrimary};
  }
`

export const StatDivider = styled.span`
  display: inline-block;
  width: 1px;
  height: 16px;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
`

export const StatIcon = styled.span<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ $color, theme }) => $color || theme.colors.textSecondary};
`

export const TabLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const TabCount = styled(Badge)<{ $color?: string }>`
  .ant-scroll-number {
    background-color: ${({ $color, theme }) => $color || theme.colors.primary};
  }
`

// ============================================
// EMPTY STATE COMPONENTS
// ============================================

export const PaddedEmpty = styled(Empty)`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
`

export const EmptyStateWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
  text-align: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const EmptyStatePanel = styled(PaddedEmpty)<{
  $align?: 'center' | 'flex-start'
  $gap?: SpacingValue
  $marginTop?: SpacingValue
  $marginBottom?: SpacingValue
}>`
  && {
    display: flex;
    flex-direction: column;
    gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
    align-items: ${({ $align = 'center' }) => $align};
    text-align: ${({ $align = 'center' }) => ($align === 'center' ? 'center' : 'left')};
    ${({ theme, $marginTop }) =>
      $marginTop !== undefined
        ? `margin-top: ${resolveSpacingValue(theme, $marginTop)}px;`
        : ''}
    ${({ theme, $marginBottom }) =>
      $marginBottom !== undefined
        ? `margin-bottom: ${resolveSpacingValue(theme, $marginBottom)}px;`
        : ''}
  }
`

export const LoadingState = styled.div<{
  $paddingY?: SpacingValue
  $gap?: SpacingValue
  $align?: 'flex-start' | 'center'
  $justify?: 'flex-start' | 'center'
  $textAlign?: 'left' | 'center'
  $muted?: boolean
}>`
  display: flex;
  flex-direction: column;
  align-items: ${({ $align = 'center' }) => $align};
  justify-content: ${({ $justify = 'center' }) => $justify};
  text-align: ${({ $textAlign = 'center' }) => $textAlign};
  padding: ${({ theme, $paddingY }) => `${resolveSpacingValue(theme, $paddingY, 'XL')}px 0`};
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
  color: ${({ theme, $muted = true }) =>
    $muted ? theme.colors.textSecondary : theme.colors.textPrimary};
`

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.PAGE_SECTION_GAP}px;
`

export const FlexColumn = styled.div<{ $gap?: SpacingValue; $align?: string; $justify?: string }>`
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'MD')}px;
  align-items: ${({ $align }) => $align || 'stretch'};
  justify-content: ${({ $justify }) => $justify || 'flex-start'};
`

export const NeutralStack = styled(FlexColumn)``

export const SectionHeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const ControlStack = styled.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  gap: ${({ theme }) => theme.spacing.MD}px;
  align-items: center;
`

export const InputSlot = styled.div`
  flex: 1 1 280px;
  min-width: 240px;
`

export const ActionBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  justify-content: flex-end;
`

export const ButtonSurface = styled(Button)<{
  $variant?: ButtonVariant
  $size?: ButtonSize
  $minWidth?: number
}>`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.MD}px;
    min-height: ${({ theme, $size }) => `${resolveButtonHeight(theme, $size)}px`};
    min-width: ${({ $minWidth }) => ($minWidth ? `${$minWidth}px` : 'auto')};
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    line-height: 1.2;
    transition: ${({ theme }) => theme.transitions.BUTTON};
    background-color: ${({ theme, $variant }) => resolveButtonVariantTokens($variant, theme).bg};
    color: ${({ theme, $variant }) => resolveButtonVariantTokens($variant, theme).color};
    border: 1px solid ${({ theme, $variant }) => resolveButtonVariantTokens($variant, theme).border};
    ${(props) =>
      props.$variant === 'link'
        ? `
      padding: 0;
      min-height: auto;
      min-width: auto;
      border: none;
      box-shadow: none;
    `
        : ''}

    &:not(:disabled):hover,
    &:not(:disabled):focus {
      background-color: ${({ theme, $variant }) => resolveButtonVariantTokens($variant, theme).hoverBg};
      color: ${({ theme, $variant }) => resolveButtonVariantTokens($variant, theme).hoverColor};
      border-color: ${({ theme, $variant }) => resolveButtonVariantTokens($variant, theme).hoverBorder};
      ${(props) =>
        props.$variant === 'link'
          ? ''
          : `
        transform: translateY(-1px);
        box-shadow: ${props.theme.shadows.BUTTON_HOVER};
      `}
    }
  }
`

export const PrimaryButton = styled(ButtonSurface).attrs({
  $variant: 'primary',
})``

export const SecondaryButton = styled(ButtonSurface).attrs({
  $variant: 'secondary',
})``

export const GhostButton = styled(ButtonSurface).attrs({
  $variant: 'ghost',
})``

export const DangerButton = styled(ButtonSurface).attrs({
  $variant: 'danger',
})``

export const LinkButton = styled(ButtonSurface).attrs({
  $variant: 'link',
})`
  && {
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const ActionButton = styled(ButtonSurface).attrs({
  $variant: 'secondary',
})`
  && {
    min-width: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT}px;
  }
`

export const PageTitle = styled(Title)`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`

export const CardTitle = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.H4}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const SectionSubtitle = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const HelperText = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const MutedCaption = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const EmptyStateTitle = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const EmptyStateDescription = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const FormLabel = styled(Text)`
  && {
    margin: 0;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const BreadcrumbWrapper = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`

export const ContentSection = styled.div`
  min-height: 400px;
`

export const DataTable = styled(Table as any)<{ $isLoading?: boolean }>`
  .ant-spin-nested-loading {
    opacity: ${(props) => (props.$isLoading ? 0.65 : 1)};
    transition: ${({ theme }) => theme.transitions.DEFAULT};
  }
`

export const SectionDescription = styled(Typography.Paragraph)`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const StatGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const InlineBadge = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`

export const CardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const SectionDivider = styled.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
  margin: ${({ theme }) => theme.spacing.LG}px 0;
`

export const ActionToolbar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const Pill = styled.span`
  display: inline-flex;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`

export const StatusBadge = styled.span<{ $variant?: StatusVariant }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
  color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
  border: 1px solid ${({ theme, $variant }) => resolveStatusTokens($variant, theme).border};
  line-height: 1;
  text-transform: none;
`

export const StatusTag = styled(Tag)<{ $variant?: StatusVariant }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).border};
    color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
    background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const PillTag = styled(Tag)<{
  $variant?: TagVariant
  $size?: TagSize
  $borderless?: boolean
}>`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    padding: ${({ theme, $size }) => resolveTagPadding(theme, $size)};
    border-radius: ${({ theme, $size }) => resolveTagRadius(theme, $size)}px;
    font-size: ${({ theme, $size }) => resolveTagFontSize(theme, $size)}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    background-color: ${({ theme, $variant }) => resolveTagVariantTokens($variant, theme).bg};
    color: ${({ theme, $variant }) => resolveTagVariantTokens($variant, theme).color};
    border: ${({ $borderless, theme, $variant }) =>
      $borderless ? 'none' : `1px solid ${resolveTagVariantTokens($variant, theme).border}`};
    line-height: 1.2;
  }
`

export const StyledIcon = styled.span<{ $size?: IconSizeValue; $color?: string; $rotate?: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size }) => `${resolveIconSize(theme, $size)}px`};
  color: ${({ $color }) => $color || 'inherit'};
  line-height: 1;
  ${({ $rotate }) => ($rotate ? `transform: rotate(${$rotate}deg);` : '')}
`

export const StatusDot = styled.span<{ $variant?: StatusVariant }>`
  width: 8px;
  height: 8px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
  flex-shrink: 0;
`

export const IconButton = styled(Button)`
  width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: ${({ theme }) => theme.transitions.BUTTON};

  &:not(:disabled):hover {
    box-shadow: ${({ theme }) => theme.shadows.BUTTON_HOVER};
    transform: translateY(-1px);
  }

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  }
`

export const CompactIconButton = styled(IconButton)`
  width: ${({ theme }) => theme.spacing['5']}px;
  height: ${({ theme }) => theme.spacing['5']}px;
  min-width: ${({ theme }) => theme.spacing['5']}px;
  min-height: ${({ theme }) => theme.spacing['5']}px;
`

export const PrimaryIconButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['6']}px;
  min-height: ${({ theme }) => theme.spacing['6']}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: ${({ theme }) => theme.colors.primary};
  border-color: ${({ theme }) => theme.colors.primary};
  color: ${({ theme }) => theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;

  &:hover,
  &:focus {
    background-color: ${({ theme }) => theme.colors.primaryHover};
    border-color: ${({ theme }) => theme.colors.primaryHover};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const SecondaryIconButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['6']}px;
  min-height: ${({ theme }) => theme.spacing['6']}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`

export const CompactButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['5']}px;
  min-height: ${({ theme }) => theme.spacing['5']}px;
`

export const InlineStack = styled.div<{ $align?: 'flex-start' | 'center' | 'flex-end' }>`
  display: inline-flex;
  align-items: ${({ $align }) => $align || 'center'};
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`

export const ScrollArea = styled.div<{ $maxHeight?: number | string }>`
  max-height: ${({ $maxHeight }) => {
    if (!$maxHeight) return 'none'
    return typeof $maxHeight === 'number' ? `${$maxHeight}px` : $maxHeight
  }};
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const PanelCard = styled.div`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
  padding: ${({ theme }) => theme.spacing.LG}px;
`

export const SectionTitleRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`

export const KeyValueGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin: 0;

  dt {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
    margin: 0;
  }

  dd {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const BaseModal = styled(Modal)`
  .ant-modal-content {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    box-shadow: ${({ theme }) => theme.shadows.MODAL};
  }

  .ant-modal-header {
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-modal-title {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }

  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.LG}px;
  }

  .ant-modal-footer {
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const ModalHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const ModalTitle = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ModalSubtitle = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`

export const ModalBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const ModalContentStack = styled.div<{ $gap?: SpacingValue }>`
  display: flex;
  flex-direction: column;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'LG')}px;
  width: 100%;
`

export const ModalFooter = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ModalFooterActions = styled.div<{ $gap?: SpacingValue; $align?: 'flex-end' | 'space-between' }>`
  display: flex;
  justify-content: ${({ $align = 'flex-end' }) => $align};
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
  width: 100%;
`

export const ModalSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ModalSectionTitle = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ModalSectionDescription = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`

export const ModalTitleRow = styled.div<{ $gap?: SpacingValue }>`
  display: flex;
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

// ============================================
// FORM CONTROL PRIMITIVES
// ============================================

export const FullWidthInput = styled(Input)`
  && {
    ${fullWidthControlStyles};
  }
`

export const FullWidthPasswordInput = styled(PasswordInput)`
  && {
    ${fullWidthControlStyles};
  }
`

export const FullWidthTextArea = styled(TextAreaInput)`
  && {
    ${fullWidthControlStyles};
  }
`

export const FullWidthInputNumber = styled(InputNumber)`
  && {
    ${fullWidthControlStyles};
  }
`

export const FullWidthSelect = styled(Select)`
  && {
    ${fullWidthControlStyles};
  }
`

export const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`

export const FormFieldRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.MD}px;
  align-items: flex-start;
`

export const FieldLabel = styled.label`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`

export const FieldDescription = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`

export const DetailList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const DetailListItem = styled.li`
  display: flex;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};

  span {
    &:first-child {
      color: ${({ theme }) => theme.colors.textSecondary};
    }
  }
`

export const InfoBanner = styled.div<{ $variant?: StatusVariant }>`
  display: flex;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
  border: 1px solid ${({ theme, $variant }) => resolveStatusTokens($variant, theme).border};
  color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
`

type AlertVariant = 'info' | 'success' | 'warning' | 'error' | 'neutral'

const resolveAlertColors = (variant: AlertVariant | undefined, theme: StyledTheme) => {
  switch (variant) {
    case 'success':
      return {
        bg: theme.colors.bgSuccess,
        border: theme.colors.success,
        color: theme.colors.success,
      }
    case 'warning':
      return {
        bg: theme.colors.bgWarning,
        border: theme.colors.warning,
        color: theme.colors.warning,
      }
    case 'error':
      return {
        bg: theme.colors.bgError,
        border: theme.colors.error,
        color: theme.colors.error,
      }
    case 'info':
      return {
        bg: theme.colors.bgInfo,
        border: theme.colors.info,
        color: theme.colors.info,
      }
    case 'neutral':
    default:
      return {
        bg: theme.colors.bgSecondary,
        border: theme.colors.borderSecondary,
        color: theme.colors.textSecondary,
      }
  }
}

export const AlertCard = styled(Alert)<{ $variant?: AlertVariant }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme, $variant }) => resolveAlertColors($variant, theme).border};
    background-color: ${({ theme, $variant }) => resolveAlertColors($variant, theme).bg};
    color: ${({ theme, $variant }) => resolveAlertColors($variant, theme).color};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};

    .ant-alert-icon {
      color: ${({ theme, $variant }) => resolveAlertColors($variant, theme).color};
    }
  }
`

export const BaseTable = styled(Table as any)<{ $isInteractive?: boolean }>`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;

  .ant-table {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-table-thead > tr > th {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    color: ${({ theme }) => theme.colors.textSecondary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }

  ${(props) =>
    props.$isInteractive
      ? `
    .ant-table-tbody > tr {
      transition: ${props.theme.transitions.DEFAULT};
    }

    .ant-table-tbody > tr:hover td {
      background-color: ${props.theme.colors.bgHover};
    }
  `
      : ''}
`

export const ModalGrid = styled.div<{ $sidebarWidth?: number }>`
  display: flex;
  gap: ${({ theme }) => theme.spacing.LG}px;
  align-items: flex-start;
  flex-wrap: wrap;

  > *:first-child {
    flex: 1 1 60%;
    min-width: min(520px, 100%);
  }

  > *:last-child {
    flex: 0 0 ${({ $sidebarWidth, theme }) =>
      $sidebarWidth ? `${$sidebarWidth}px` : `${theme.spacing.XL * 4}px`};
    min-width: 280px;
  }
`

export const ScrollablePanel = styled.div<{ $maxHeight?: number }>`
  max-height: ${({ $maxHeight }) => ($maxHeight ? `${$maxHeight}px` : '60vh')};
  overflow-y: auto;
  padding-right: ${({ theme }) => theme.spacing.SM}px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-thumb {
    background-color: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`
