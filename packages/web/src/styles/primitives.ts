import type { ComponentType } from 'react';
import { Row, Segmented, Table, Typography } from 'antd';
import styled, { css, keyframes } from 'styled-components';
// Import Rediacc components directly to avoid circular dependencies
// (barrel export @/components/ui includes card.tsx which imports from primitives)
import { RediaccAlert } from '@/components/ui/Alert';
import { RediaccBadge } from '@/components/ui/Badge';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccCard } from '@/components/ui/Card';
import { RediaccEmpty } from '@/components/ui/Empty';
// Import unified form components
import {
  RediaccCheckbox,
  RediaccDatePicker,
  RediaccInput,
  RediaccPasswordInput,
  RediaccSearchInput,
  RediaccSelect,
} from '@/components/ui/Form';
import { RediaccModal } from '@/components/ui/Modal';
import { RediaccTag } from '@/components/ui/Tag';
import { RediaccText } from '@/components/ui/Text';
import { borderedCard } from '@/styles/mixins';
import type { StyledTheme } from '@/styles/styledTheme';
import { RightOutlined } from '@/utils/optimizedIcons';
import type { TableProps } from 'antd';

// ============================================
// SHARED ANIMATIONS
// ============================================

export const fadeInAnimation = keyframes`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

// ============================================
// SHARED CSS HELPERS
// ============================================

export const scrollbarStyles = css`
  &::-webkit-scrollbar {
    width: ${({ theme }) => theme.spacing.SM}px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const inputFocusStyles = css`
  &:focus,
  &.ant-input-affix-wrapper-focused {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    outline: none;
  }

  &.ant-input-status-error,
  &.ant-input-affix-wrapper-status-error {
    border-color: ${({ theme }) => theme.colors.error};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.error};
  }
`;

export const inputPrefixStyles = css`
  .ant-input-prefix {
    margin-left: ${({ theme }) => theme.spacing.SM_LG}px;
    margin-right: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textTertiary};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    transition: color 0.2s ease;

    .anticon {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }

  .ant-input-suffix {
    margin-right: ${({ theme }) => theme.spacing.SM_LG}px;
  }

  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
    color: ${({ theme }) => theme.colors.primary};
  }
`;

const GenericTable = Table as ComponentType<TableProps<unknown>>;

export type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'processing';
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
  | 'processing';
export type TagSize = 'SM' | 'MD';
export type IconSize = 'SM' | 'MD' | 'LG' | 'XL' | 'XXL' | 'XXXL';
type IconSizeValue = IconSize | number;
type ColorKey = keyof StyledTheme['colors'];

type SpacingScale = StyledTheme['spacing'];
type SpacingToken = keyof SpacingScale;
type SpacingValue = SpacingToken | number;

const resolveSpacingValue = (
  theme: StyledTheme,
  value?: SpacingValue,
  fallback: SpacingToken = 'MD'
) => {
  if (typeof value === 'number') {
    return value;
  }
  const token = (value || fallback) as SpacingToken;
  return theme.spacing[token];
};

type StatusTokenKeys = { bg: ColorKey; color: ColorKey; border?: ColorKey };

const STATUS_TOKEN_KEYS: Record<StatusVariant, StatusTokenKeys> = {
  success: { bg: 'bgSuccess', color: 'success' },
  warning: { bg: 'bgWarning', color: 'warning' },
  error: { bg: 'bgError', color: 'error' },
  processing: { bg: 'primaryBg', color: 'primary' },
  neutral: { bg: 'bgSecondary', color: 'textSecondary', border: 'borderSecondary' },
  info: { bg: 'bgInfo', color: 'info' },
};

const resolveStatusTokens = (variant: StatusVariant = 'info', theme: StyledTheme) => {
  const tokens = STATUS_TOKEN_KEYS[variant] || STATUS_TOKEN_KEYS.info;
  const colorKey = tokens.color;
  const borderKey = tokens.border || colorKey;

  return {
    bg: theme.colors[tokens.bg],
    color: theme.colors[colorKey],
    border: theme.colors[borderKey],
  };
};

const resolveIconSize = (theme: StyledTheme, size?: IconSizeValue) => {
  if (typeof size === 'number') {
    return size;
  }
  const token = size || 'MD';
  switch (token) {
    case 'SM':
      return theme.dimensions.ICON_SM;
    case 'LG':
      return theme.dimensions.ICON_LG;
    case 'XL':
      return theme.dimensions.ICON_XL;
    case 'XXL':
      return theme.dimensions.ICON_XXL;
    case 'XXXL':
      return theme.dimensions.ICON_XXXL;
    case 'MD':
    default:
      return theme.dimensions.ICON_MD;
  }
};

type FontWeightScale = StyledTheme['fontWeight'];
type FontWeightToken = keyof FontWeightScale;

const resolveFontWeight = (theme: StyledTheme, value?: FontWeightToken | number) => {
  if (typeof value === 'number') {
    return value;
  }
  const token = (value || 'SEMIBOLD') as FontWeightToken;
  return theme.fontWeight[token];
};

type DimensionScale = StyledTheme['dimensions'];
type DimensionToken = keyof DimensionScale;

const resolveDimensionValue = (
  theme: StyledTheme,
  value?: DimensionToken | number,
  fallback: DimensionToken = 'ICON_SM'
) => {
  if (typeof value === 'number') {
    return value;
  }
  const token = (value || fallback) as DimensionToken;
  return theme.dimensions[token];
};

export const PageContainer = styled.div.attrs({ className: 'page-container' })`
  width: 100%;
`;

export const PageCard = styled(RediaccCard).attrs({ className: 'page-card' })``;

// ============================================
// TABLE PRIMITIVES
// ============================================

export const IconActionButton = styled(RediaccButton).attrs({ iconOnly: true, size: 'sm' })`
  && {
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border: none;
    background: transparent;
    box-shadow: none;
    color: ${({ theme }) => theme.colors.textPrimary};
    transition: background ${({ theme }) => theme.transitions.FAST};
    &:hover, &:focus {
      background: var(--color-fill-tertiary);
    }
  }
`;

export const ExpandIcon = styled(RightOutlined)<{
  $expanded?: boolean;
  $visible?: boolean;
  $color?: string;
  $size?: DimensionToken | number;
}>`
  font-size: ${({ theme, $size }) => `${resolveDimensionValue(theme, $size)}px`};
  color: ${({ theme, $color }) => $color || theme.colors.textTertiary};
  transition: transform ${({ theme }) => theme.transitions.FAST};
  transform: ${({ $expanded }) => ($expanded ? 'rotate(90deg)' : 'rotate(0deg)')};
  visibility: ${({ $visible = true }) => ($visible ? 'visible' : 'hidden')};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;

export const TableContainer = styled.div`
  ${borderedCard()}
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
`;

export const TableCellContent = styled.span<{ $gap?: SpacingValue }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
`;

export const TableCellText = styled.span<{
  $muted?: boolean;
  $weight?: FontWeightToken | number;
}>`
  font-weight: ${({ theme, $weight }) => resolveFontWeight(theme, $weight)};
  color: ${({ theme, $muted }) => ($muted ? theme.colors.textSecondary : theme.colors.textPrimary)};
`;

// ============================================
// FILTER COMPONENTS
// ============================================

export const FilterSelect = styled(RediaccSelect)<{ $minWidth?: number }>`
  min-width: ${({ $minWidth }) => ($minWidth ? `${$minWidth}px` : '150px')};
`;

export const FilterRangePicker = styled(RediaccDatePicker.RangePicker)`
  min-width: 220px;
`;

export const FilterInput = styled(RediaccInput)`
  min-width: ${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px;
`;

export const FilterCheckbox = styled(RediaccCheckbox)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

// ============================================
// STATS COMPONENTS
// ============================================

// Resolve variant to theme color
const resolveStatVariantColor = (
  variant: StatusVariant | undefined,
  theme: StyledTheme
): string => {
  if (!variant) return theme.colors.textPrimary;
  switch (variant) {
    case 'success':
      return theme.colors.success;
    case 'warning':
      return theme.colors.warning;
    case 'error':
      return theme.colors.error;
    case 'info':
      return theme.colors.info;
    default:
      return theme.colors.textPrimary;
  }
};

export const StatValue = styled(RediaccText).attrs(() => ({
  variant: 'caption',
  weight: 'semibold',
}))<{ $color?: string; $variant?: StatusVariant }>`
  && {
    color: ${({ $color, $variant, theme }) => $color || resolveStatVariantColor($variant, theme)};
  }
`;

export const StatDivider = styled.span`
  display: inline-block;
  width: 1px;
  height: ${({ theme }) => theme.spacing.MD}px;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
`;

export const StatIcon = styled.span<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ $color, theme }) => $color || theme.colors.textSecondary};
`;

export const TabLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const TabCount = styled(RediaccBadge)<{ $color?: string }>`
  .ant-scroll-number {
    background-color: ${({ $color, theme }) => $color || theme.colors.primary};
  }
`;

// ============================================
// EMPTY STATE COMPONENTS
// ============================================

export const EmptyStateWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
  text-align: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const EmptyStatePanel = styled(RediaccEmpty)<{
  $align?: 'center' | 'flex-start';
  $gap?: SpacingValue;
  $marginTop?: SpacingValue;
  $marginBottom?: SpacingValue;
}>`
  && {
    display: flex;
    flex-direction: column;
    gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
    align-items: ${({ $align = 'center' }) => $align};
    text-align: ${({ $align = 'center' }) => ($align === 'center' ? 'center' : 'left')};
    ${({ theme, $marginTop }) =>
      $marginTop !== undefined ? `margin-top: ${resolveSpacingValue(theme, $marginTop)}px;` : ''}
    ${({ theme, $marginBottom }) =>
      $marginBottom !== undefined
        ? `margin-bottom: ${resolveSpacingValue(theme, $marginBottom)}px;`
        : ''}
  }
`;

export const StyledEmpty = styled(RediaccEmpty)`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
`;

export const LoadingState = styled.div<{
  $paddingY?: SpacingValue;
  $gap?: SpacingValue;
  $align?: 'flex-start' | 'center';
  $justify?: 'flex-start' | 'center';
  $textAlign?: 'left' | 'center';
  $muted?: boolean;
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
`;

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.PAGE_SECTION_GAP}px;
`;

const InternalFlexColumn = styled.div<{ $gap?: SpacingValue; $align?: string; $justify?: string }>`
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'MD')}px;
  align-items: ${({ $align }) => $align || 'stretch'};
  justify-content: ${({ $justify }) => $justify || 'flex-start'};
`;

export const NeutralStack = styled(InternalFlexColumn)``;

export const SectionHeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const ControlStack = styled.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  gap: ${({ theme }) => theme.spacing.MD}px;
  align-items: center;
`;

export const InputSlot = styled.div`
  flex: 1 1 280px;
  min-width: 240px;
`;

export const ActionBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  justify-content: flex-end;
`;

export const CaptionText = styled(RediaccText).attrs<{ $muted?: boolean; $size?: number }>(
  ({ $muted }) => ({
    variant: 'caption',
    color: $muted ? 'secondary' : 'primary',
  })
)<{ $muted?: boolean; $size?: number }>`
  && {
    margin: 0;
    ${({ $size }) => ($size !== undefined ? `font-size: ${$size}px;` : '')}
  }
`;

export const ContentSection = styled.div`
  min-height: ${({ theme }) => theme.dimensions.CONTENT_MIN_HEIGHT}px;
`;

export const StatusTag = styled(RediaccTag)<{ $variant?: StatusVariant }>`
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
`;

export const StyledIcon = styled.span<{ $size?: IconSizeValue; $color?: string; $rotate?: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size }) => `${resolveIconSize(theme, $size)}px`};
  color: ${({ $color }) => $color || 'inherit'};
  line-height: 1;
  ${({ $rotate }) => ($rotate ? `transform: rotate(${$rotate}deg);` : '')}
`;

export const BaseModal = styled(RediaccModal)`
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
`;

export const ModalHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const ModalTitle = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ModalSubtitle = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const ModalBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const ModalContentStack = styled.div<{ $gap?: SpacingValue }>`
  display: flex;
  flex-direction: column;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'LG')}px;
  width: 100%;
`;

export const ModalFooterActions = styled.div<{
  $gap?: SpacingValue;
  $align?: 'flex-end' | 'space-between';
}>`
  display: flex;
  justify-content: ${({ $align = 'flex-end' }) => $align};
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
  width: 100%;
`;

export const ModalTitleRow = styled.div<{ $gap?: SpacingValue }>`
  display: flex;
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

// ============================================
// ALERT VARIANTS
// ============================================

type AlertVariant = 'info' | 'success' | 'warning' | 'error' | 'neutral';

const resolveAlertColors = (variant: AlertVariant | undefined, theme: StyledTheme) => {
  switch (variant) {
    case 'success':
      return {
        bg: theme.colors.bgSuccess,
        border: theme.colors.success,
        color: theme.colors.success,
      };
    case 'warning':
      return {
        bg: theme.colors.bgWarning,
        border: theme.colors.warning,
        color: theme.colors.warning,
      };
    case 'error':
      return {
        bg: theme.colors.bgError,
        border: theme.colors.error,
        color: theme.colors.error,
      };
    case 'info':
      return {
        bg: theme.colors.bgInfo,
        border: theme.colors.info,
        color: theme.colors.info,
      };
    case 'neutral':
    default:
      return {
        bg: theme.colors.bgSecondary,
        border: theme.colors.borderSecondary,
        color: theme.colors.textSecondary,
      };
  }
};

export const AlertCard = styled(RediaccAlert)<{ $variant?: AlertVariant }>`
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
`;

export const BaseTable = styled(GenericTable)<{ $isInteractive?: boolean }>`
  ${borderedCard()}
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
`;

// ============================================
// ADDITIONAL CARD VARIANTS
// ============================================

export const ContentCard = styled(RediaccCard)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const FeatureCard = styled(ContentCard)`
  && {
    height: 100%;
  }
`;

export const SelectableCard = styled(RediaccCard)<{
  $selected?: boolean;
  $variant?: 'default' | 'dashed';
}>`
  && {
    border-color: ${({ theme, $selected }) => ($selected ? theme.colors.primary : theme.colors.borderSecondary)};
    border-width: ${({ $selected }) => ($selected ? '2px' : '1px')};
    border-style: ${({ $variant }) => ($variant === 'dashed' ? 'dashed' : 'solid')};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    cursor: pointer;
    transition: ${({ theme }) => theme.transitions.HOVER};

    &:hover {
      border-color: ${({ theme }) => theme.colors.primary};
      box-shadow: ${({ theme }) => theme.shadows.SM};
    }
  }
`;

// ============================================
// ADDITIONAL TEXT VARIANTS
// ============================================

export const TitleText = styled(RediaccText).attrs({ weight: 'semibold', color: 'primary' })<{
  $level?: 1 | 2 | 3 | 4 | 5;
}>`
  && {
    margin: 0;
    font-size: ${({ theme, $level = 4 }) => {
      // Map level to available font sizes
      const sizes: Record<number, number> = {
        1: theme.fontSize.XXXXXXL, // Largest available
        2: theme.fontSize.XL,
        3: theme.fontSize.LG,
        4: theme.fontSize.H4,
        5: theme.fontSize.H5,
      };
      return sizes[$level] || theme.fontSize.H4;
    }}px;
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
  }
`;

export const NoMarginTitle = styled(Typography.Title)`
  && {
    margin: 0;
  }
`;

// ============================================
// ADDITIONAL LAYOUT PATTERNS
// ============================================

export const FlexRow = styled.div<{
  $gap?: SpacingValue;
  $align?: 'flex-start' | 'center' | 'flex-end' | 'stretch';
  $justify?: 'flex-start' | 'center' | 'flex-end' | 'space-between' | 'space-around';
  $wrap?: boolean;
}>`
  display: flex;
  flex-direction: row;
  align-items: ${({ $align = 'center' }) => $align};
  justify-content: ${({ $justify = 'flex-start' }) => $justify};
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
  ${({ $wrap }) => $wrap && 'flex-wrap: wrap;'}
`;

export const FlexColumn = styled.div<{
  $gap?: SpacingValue;
  $align?: 'flex-start' | 'center' | 'flex-end' | 'stretch';
}>`
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'MD')}px;
  align-items: ${({ $align = 'stretch' }) => $align};
`;

export const FlexStackXS = styled(FlexColumn).attrs({ $gap: 'XS' })``;
export const FlexStackSM = styled(FlexColumn).attrs({ $gap: 'SM' })``;
export const FlexStackMD = styled(FlexColumn).attrs({ $gap: 'MD' })``;
export const FlexStackLG = styled(FlexColumn).attrs({ $gap: 'LG' })``;

export const HeaderRow = styled(FlexRow).attrs({ $justify: 'space-between', $wrap: true })`
  width: 100%;
`;

export const CenteredContent = styled.div`
  text-align: center;
`;

export const CenteredRow = styled(Row)`
  text-align: center;
`;

// ============================================
// SCROLLABLE CONTAINERS
// ============================================

export const ScrollContainer = styled.div<{ $maxHeight?: number }>`
  max-height: ${({ theme, $maxHeight }) =>
    $maxHeight ? `${$maxHeight}px` : `${theme.dimensions.LIST_MAX_HEIGHT}px`};
  overflow-y: auto;
  ${scrollbarStyles}
`;

export const ConsoleOutput = styled.div<{ $height?: number }>`
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  height: ${({ theme, $height }) =>
    $height ? `${$height}px` : `${theme.dimensions.LIST_MAX_HEIGHT}px`};
  overflow-y: auto;
  ${scrollbarStyles}
`;

// ============================================
// MODAL VARIANTS
// ============================================

export const FadeInModal = styled(BaseModal)`
  .ant-modal-content {
    animation: ${fadeInAnimation} 0.3s ease-in-out;
  }
`;

export const LargeModal = styled(FadeInModal)`
  &.ant-modal {
    max-width: ${({ theme }) => theme.dimensions.MAX_CONTENT_WIDTH}px;
    width: ${({ theme }) => theme.dimensions.MAX_CONTENT_WIDTH}px;
  }

  .ant-modal-body {
    max-height: 80vh;
    overflow-y: auto;
  }
`;

export const ModalTitleContainer = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.MD}px;
  padding-right: ${({ theme }) => theme.spacing.XL}px;
`;

export const ModalTitleLeft = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex: 1;
  min-width: 0;
`;

export const ModalTitleRight = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: ${({ theme }) => theme.spacing.XS}px;
  flex-shrink: 0;
`;

// ============================================
// INPUT VARIANTS
// ============================================

export const LargeInput = styled(RediaccInput)`
  && {
    height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    &.ant-input-affix-wrapper {
      padding: 0;
    }

    input.ant-input {
      padding: 0 ${({ theme }) => theme.spacing.SM_LG}px;
      height: 100%;
    }

    ${inputPrefixStyles}
    ${inputFocusStyles}
  }
`;

export const LargePasswordInput = styled(RediaccPasswordInput)`
  && {
    height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;

    &.ant-input-affix-wrapper {
      padding: 0;
    }

    input.ant-input {
      padding: 0 ${({ theme }) => theme.spacing.SM_LG}px;
      height: 100%;
    }

    ${inputPrefixStyles}

    .ant-input-suffix {
      margin-left: ${({ theme }) => theme.spacing.SM}px;

      .ant-input-password-icon {
        color: ${({ theme }) => theme.colors.textTertiary};
        font-size: ${({ theme }) => theme.fontSize.LG}px;
        transition: ${({ theme }) => theme.transitions.DEFAULT};
        cursor: pointer;
        padding: ${({ theme }) => theme.spacing.XS}px;
        border-radius: ${({ theme }) => theme.borderRadius.SM}px;

        &:hover {
          color: ${({ theme }) => theme.colors.textSecondary};
          background-color: ${({ theme }) => theme.colors.bgHover};
        }
      }
    }

    ${inputFocusStyles}
  }
`;

/**
 * @deprecated Use SearchInput from @/components/ui/Form instead
 */
export const SearchInput = styled(RediaccSearchInput)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

// ============================================
// LOADING COMPONENTS
// ============================================

export const LoadingContainer = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.XXXL}px 0;
`;

export const LoadingText = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

// ============================================
// MISC COMPONENTS
// ============================================

export const ModeSegmented = styled(Segmented)`
  min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
`;

export const LastFetchedText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  white-space: nowrap;
`;

export const SectionMargin = styled.div<{ $top?: number; $bottom?: number }>`
  ${({ $top }) => ($top !== undefined ? `margin-top: ${$top}px;` : '')}
  ${({ $bottom }) => ($bottom !== undefined ? `margin-bottom: ${$bottom}px;` : '')}
`;

export const CenteredFooter = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  text-align: center;
`;

export const InfoList = styled.ul<{ $top?: number; $bottom?: number }>`
  padding-left: ${({ theme }) => theme.spacing.LG}px;
  ${({ $top }) => ($top !== undefined ? `margin-top: ${$top}px;` : '')}
  ${({ $bottom }) => ($bottom !== undefined ? `margin-bottom: ${$bottom}px;` : '')}
`;
