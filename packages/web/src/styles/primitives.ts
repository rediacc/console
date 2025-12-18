import { Segmented } from 'antd';
import styled, { css } from 'styled-components';
// Import Rediacc components directly to avoid circular dependencies
// (barrel export @/components/ui includes card.tsx which imports from primitives)
import { RediaccAlert } from '@/components/ui/Alert';
import { RediaccBadge } from '@/components/ui/Badge';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccCard } from '@/components/ui/Card';
import { RediaccEmpty } from '@/components/ui/Empty';
// Import unified form components
import {
  RediaccDatePicker,
  RediaccInput,
  RediaccPasswordInput,
  RediaccSelect,
} from '@/components/ui/Form';
import { RediaccModal } from '@/components/ui/Modal';
import { RediaccTag } from '@/components/ui/Tag';
import { RediaccText } from '@/components/ui/Text';
import type { StyledTheme } from '@/styles/styledTheme';
import { RightOutlined } from '@/utils/optimizedIcons';

/**
 * ============================================================
 * HYBRID STYLING ARCHITECTURE - TIER 3 COMPONENTS
 * ============================================================
 *
 * This file uses a hybrid approach where most components are in pure CSS
 * in separate files, but 12 Tier 3 components remain in styled-components (JS)
 * due to complex color resolution and theme logic that is cleaner and more
 * maintainable in JavaScript.
 *
 * TIER 3 COMPONENTS (Remaining in styled-components):
 *
 * 1. StatusTag - resolveStatusTokens() with 6 variants
 * 2. AlertCard - resolveAlertColors() with 5 variants + nested icon colors
 * 3. StatValue - resolveStatVariantColor() variant-based
 * 4. StatDivider - Part of Stat* family, simple but tightly coupled
 * 5. BaseModal - Nested Ant Design selectors, specificity requirements
 * 6. FadeInModal - Inherits from BaseModal
 * 7. LargeModal - Inherits from FadeInModal
 * 8. LargeInput - inputPrefixStyles + inputFocusStyles helpers
 * 9. LargePasswordInput - Complex nested hover states
 * 10. ExpandIcon - Dynamic $color prop with fallback
 * 11. StatIcon - Dynamic $color prop with fallback
 * 12. StyledIcon - Dynamic $color prop or inherit
 *
 * RATIONALE: JavaScript-based color resolution and conditional logic would
 * require significant duplication or complex CSS variables if moved to pure CSS.
 * The styled-components approach provides:
 * - Clean color resolution functions
 * - Readable conditional logic for props
 * - Avoids CSS variable bloat
 * - Single source of truth for variant definitions
 * - Cleaner inheritance chains
 * - Better TypeScript integration
 */

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
  }

  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const inputFocusStyles = css`
  &:focus,
  &.ant-input-affix-wrapper-focused {
    outline: none;
  }

  &.ant-input-status-error,
  &.ant-input-affix-wrapper-status-error {
  }
`;

export const inputPrefixStyles = css`
  .ant-input-prefix {
    color: ${({ theme }) => theme.colors.textTertiary};
    font-size: ${({ theme }) => theme.fontSize.LG}px;

    .anticon {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }

  .ant-input-suffix {
  }

  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
    color: ${({ theme }) => theme.colors.primary};
  }
`;

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
  neutral: { bg: 'bgPrimary', color: 'textSecondary', border: 'borderSecondary' },
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

const ICON_SIZE_MAP: Record<IconSize, keyof StyledTheme['dimensions']> = {
  SM: 'ICON_SM',
  MD: 'ICON_MD',
  LG: 'ICON_LG',
  XL: 'ICON_XL',
  XXL: 'ICON_XXL',
  XXXL: 'ICON_XXXL',
};

const resolveIconSize = (theme: StyledTheme, size?: IconSizeValue) => {
  if (typeof size === 'number') {
    return size;
  }
  const token = size || 'MD';
  return theme.dimensions[ICON_SIZE_MAP[token] || ICON_SIZE_MAP.MD];
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

export const IconActionButton = styled(RediaccButton).attrs({
  iconOnly: true,
  className: 'icon-action-button',
})`
  && {
    width: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    min-width: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

/**
 * ExpandIcon - TIER 3 - styled-components
 * Reason: Dynamic $color prop with fallback to theme.colors.textTertiary
 * Uses resolveDimensionValue() for size resolution. Clean prop-based API.
 */
export const ExpandIcon = styled(RightOutlined)<{
  $expanded?: boolean;
  $visible?: boolean;
  $color?: string;
  $size?: DimensionToken | number;
}>`
  font-size: ${({ theme, $size }) => `${resolveDimensionValue(theme, $size)}px`};
  color: ${({ theme, $color }) => $color || theme.colors.textTertiary};
  visibility: ${({ $visible = true }) => ($visible ? 'visible' : 'hidden')};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;

// ============================================
// FILTER COMPONENTS
// ============================================

export const FilterSelect = styled(RediaccSelect)<{ $minWidth?: number }>`
  min-width: ${({ $minWidth, theme }) =>
    $minWidth ? `${$minWidth}px` : `${theme.dimensions.LOGO_MAX_WIDTH}px`};
`;

export const FilterRangePicker = styled(RediaccDatePicker.RangePicker)`
  min-width: ${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px;
`;

export const FilterInput = styled(RediaccInput)`
  min-width: ${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px;
`;

// ============================================
// STATS COMPONENTS
// ============================================

const STAT_VARIANT_COLOR_MAP: Partial<Record<StatusVariant, keyof StyledTheme['colors']>> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'info',
};

// Resolve variant to theme color
const resolveStatVariantColor = (
  variant: StatusVariant | undefined,
  theme: StyledTheme
): string => {
  if (!variant) return theme.colors.textPrimary;
  const colorKey = STAT_VARIANT_COLOR_MAP[variant];
  return colorKey ? theme.colors[colorKey] : theme.colors.textPrimary;
};

/**
 * StatValue - TIER 3 - styled-components
 * Reason: resolveStatVariantColor() maps variant to theme color with logic
 * Cleaner than CSS variant classes + supports color prop override
 */
export const StatValue = styled(RediaccText).attrs(() => ({
  variant: 'caption',
  weight: 'semibold',
}))<{ $color?: string; $variant?: StatusVariant }>`
  && {
    color: ${({ $color, $variant, theme }) => $color || resolveStatVariantColor($variant, theme)};
  }
`;

/**
 * StatDivider - TIER 3 - styled-components
 * Reason: Part of Stat* family (StatValue, StatDivider, StatIcon). Semantic grouping.
 * Tightly coupled with other stat components.
 */
export const StatDivider = styled.span`
  display: inline-block;
  width: 1px;
  height: ${({ theme }) => theme.spacing.MD}px;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
`;

/**
 * StatIcon - TIER 3 - styled-components
 * Reason: Part of Stat* family with dynamic $color prop and fallback
 * Keeps related stat components together for maintainability
 */
export const StatIcon = styled.span<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ $color, theme }) => $color || theme.colors.textSecondary};
`;

export const TabLabel = styled.span`
  display: inline-flex;
  align-items: center;
`;

export const TabCount = styled(RediaccBadge)<{ $color?: string }>`
  .ant-scroll-number {
    background-color: ${({ $color, theme }) => $color || theme.colors.primary};
  }
`;

// ============================================
// EMPTY STATE COMPONENTS
// ============================================

export const EmptyStateWrapper = styled.div.attrs({
  className: 'empty-state-wrapper',
})`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
  text-align: center;
`;

export const EmptyStatePanel = styled(RediaccEmpty)<{
  $align?: 'center' | 'flex-start';
}>`
  && {
    display: flex;
    flex-direction: column;
    align-items: ${({ $align = 'center' }) => $align};
    text-align: ${({ $align = 'center' }) => ($align === 'center' ? 'center' : 'left')};
  }
`;

export const StyledEmpty = styled(RediaccEmpty)`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
`;

export const LoadingState = styled.div.attrs<{
  $paddingY?: SpacingValue;
  $align?: 'flex-start' | 'center';
  $justify?: 'flex-start' | 'center';
  $textAlign?: 'left' | 'center';
  $muted?: boolean;
}>(({ $muted = true }) => ({
  className: $muted ? 'loading-state loading-state-muted' : 'loading-state',
}))<{
  $paddingY?: SpacingValue;
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
`;

export const SectionStack = styled.div.attrs({ className: 'section-stack' })`
`;

export const SectionHeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
`;

export const ControlStack = styled.div.attrs({ className: 'control-stack' })`
`;

export const InputSlot = styled.div.attrs({ className: 'input-slot' })`
  flex: 1 1 280px;
  min-width: ${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH_SM}px;
`;

export const ActionBar = styled.div.attrs({ className: 'action-bar' })`
`;

export const CaptionText = styled(RediaccText).attrs<{ $muted?: boolean; $size?: number }>(
  ({ $muted }) => ({
    variant: 'caption',
    color: $muted ? 'secondary' : 'primary',
  })
)<{ $muted?: boolean; $size?: number }>`
  && {
    ${({ $size }) => ($size !== undefined ? `font-size: ${$size}px;` : '')}
  }
`;

export const ContentSection = styled.div.attrs({ className: 'content-section' })`
  min-height: ${({ theme }) => theme.dimensions.CONTENT_MIN_HEIGHT}px;
`;

/**
 * StatusTag - TIER 3 - styled-components
 * Reason: resolveStatusTokens() maps 6 variants (success, warning, error, processing, neutral, info)
 * to theme colors. JavaScript logic cleaner than maintaining 6+ CSS classes with duplicate styles.
 */
export const StatusTag = styled(RediaccTag)<{ $variant?: StatusVariant }>`
  && {
    color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
    background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    display: inline-flex;
    align-items: center;
  }
`;

/**
 * StyledIcon - TIER 3 - styled-components
 * Reason: Dynamic $color prop with 'inherit' fallback. resolveIconSize() for size resolution.
 * Flexible icon styling across codebase. TypeScript validation improves prop API.
 */
export const StyledIcon = styled.span<{ $size?: IconSizeValue; $color?: string; $rotate?: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size }) => `${resolveIconSize(theme, $size)}px`};
  color: ${({ $color }) => $color || 'inherit'};
  line-height: 1;
`;

/**
 * BaseModal - TIER 3 - styled-components
 * Reason: Complex nested Ant Design selectors (.ant-modal-content, .ant-modal-header, .ant-modal-title,
 * .ant-modal-body, .ant-modal-footer). Each needs independent background and text color theming.
 * Inheritance chain (BaseModal -> FadeInModal -> LargeModal) cleaner in styled-components.
 */
export const BaseModal = styled(RediaccModal)`
  .ant-modal-content {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-modal-header {
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
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    display: flex;
    justify-content: flex-end;
    align-items: center;
  }
`;

export const ModalHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
`;

export const ModalTitle = styled.div.attrs({
  className: 'modal-title',
})`
  display: flex;
  flex-direction: column;
`;

export const ModalSubtitle = styled.span.attrs({
  className: 'modal-subtitle',
})`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const ModalBody = styled.div`
  display: flex;
  flex-direction: column;
`;

export const ModalContentStack = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const ModalFooterActions = styled.div<{
  $align?: 'flex-end' | 'space-between';
}>`
  display: flex;
  justify-content: ${({ $align = 'flex-end' }) => $align};
  align-items: center;
  width: 100%;
`;

export const ModalTitleRow = styled.div.attrs({
  className: 'modal-title-row',
})`
  display: flex;
  align-items: center;
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

// ============================================
// ALERT VARIANTS
// ============================================

type AlertVariant = 'info' | 'success' | 'warning' | 'error' | 'neutral';

type AlertColorKeys = {
  bg: keyof StyledTheme['colors'];
  border: keyof StyledTheme['colors'];
  color: keyof StyledTheme['colors'];
};

const ALERT_COLORS_MAP: Record<AlertVariant, AlertColorKeys> = {
  success: { bg: 'bgSuccess', border: 'success', color: 'success' },
  warning: { bg: 'bgWarning', border: 'warning', color: 'warning' },
  error: { bg: 'bgError', border: 'error', color: 'error' },
  info: { bg: 'bgInfo', border: 'info', color: 'info' },
  neutral: { bg: 'bgPrimary', border: 'borderSecondary', color: 'textSecondary' },
};

const resolveAlertColors = (variant: AlertVariant | undefined, theme: StyledTheme) => {
  const keys = ALERT_COLORS_MAP[variant || 'neutral'];
  return {
    bg: theme.colors[keys.bg],
    border: theme.colors[keys.border],
    color: theme.colors[keys.color],
  };
};

/**
 * AlertCard - TIER 3 - styled-components
 * Reason: resolveAlertColors() maps 5 variants (success, warning, error, info, neutral) to theme colors.
 * Styles nested .ant-alert-icon with consistent color from variant.
 */
export const AlertCard = styled(RediaccAlert)<{ $variant?: AlertVariant }>`
  && {
    background-color: ${({ theme, $variant }) => resolveAlertColors($variant, theme).bg};
    color: ${({ theme, $variant }) => resolveAlertColors($variant, theme).color};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};

    .ant-alert-icon {
      color: ${({ theme, $variant }) => resolveAlertColors($variant, theme).color};
    }
  }
`;

// ============================================
// ADDITIONAL CARD VARIANTS
// ============================================

export const FeatureCard = styled(RediaccCard)`
  && {
    height: 100%;
  }
`;

export const SelectableCard = styled(RediaccCard)<{
  $selected?: boolean;
  $variant?: 'default' | 'dashed';
}>`
  && {
    cursor: pointer;
  }
`;

// ============================================
// ADDITIONAL TEXT VARIANTS
// ============================================

export const TitleText = styled(RediaccText).attrs({ weight: 'semibold', color: 'primary' })<{
  $level?: 1 | 2 | 3 | 4 | 5;
}>`
  && {
    font-size: ${({ theme, $level = 4 }) => {
      // Map level to available font sizes
      const sizes: Record<number, number> = {
        1: theme.fontSize.DISPLAY, // Largest available
        2: theme.fontSize.XL,
        3: theme.fontSize.LG,
        4: theme.fontSize.XL,
        5: theme.fontSize.LG,
      };
      return sizes[$level] || theme.fontSize.XL;
    }}px;
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
  }
`;

// ============================================
// ADDITIONAL LAYOUT PATTERNS
// ============================================

export const FlexRow = styled.div.attrs<{
  $align?: 'flex-start' | 'center' | 'flex-end' | 'stretch';
  $justify?: 'flex-start' | 'center' | 'flex-end' | 'space-between' | 'space-around';
  $wrap?: boolean;
}>(({ $wrap }) => ({
  className: 'flex-row',
  'data-wrap': $wrap ? 'true' : undefined,
}))<{
  $align?: 'flex-start' | 'center' | 'flex-end' | 'stretch';
  $justify?: 'flex-start' | 'center' | 'flex-end' | 'space-between' | 'space-around';
  $wrap?: boolean;
}>`
  align-items: ${({ $align = 'center' }) => $align};
  justify-content: ${({ $justify = 'flex-start' }) => $justify};
`;

export const FlexColumn = styled.div.attrs({ className: 'flex-column' })<{
  $align?: 'flex-start' | 'center' | 'flex-end' | 'stretch';
}>`
  align-items: ${({ $align = 'stretch' }) => $align};
`;

export const HeaderRow = styled(FlexRow).attrs({ $justify: 'space-between', $wrap: true })`
  width: 100%;
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

export const ConsoleOutput = styled.div.attrs({
  className: 'console-output',
})<{ $height?: number }>`
  padding: ${({ theme }) => theme.spacing.SM}px;
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  line-height: ${({ theme }) => theme.lineHeight.NORMAL};
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

/**
 * FadeInModal - TIER 3 - styled-components
 * Reason: Extends BaseModal. Inherits all base modal styles.
 * Note: Animation removed as part of opacity removal initiative.
 */
export const FadeInModal = styled(BaseModal)`
  .ant-modal-content {
  }
`;

/**
 * LargeModal - TIER 3 - styled-components
 * Reason: Three-level inheritance (BaseModal -> FadeInModal -> LargeModal).
 * Adds dimension overrides while inheriting animation and base styles.
 * Flattening would require duplicating all parent styles in CSS.
 */
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
  padding-right: ${({ theme }) => theme.spacing.XL}px;
`;

export const ModalTitleLeft = styled.div`
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
`;

export const ModalTitleRight = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
`;

// ============================================
// INPUT VARIANTS
// ============================================

/**
 * LargeInput - TIER 3 - styled-components
 * Reason: Composes inputPrefixStyles and inputFocusStyles helper mixins with dimension overrides.
 * Clean composition pattern cleaner than duplicating styles in separate CSS files.
 */
export const LargeInput = styled(RediaccInput)`
  && {
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-size: ${({ theme }) => theme.fontSize.MD}px;

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

/**
 * LargePasswordInput - TIER 3 - styled-components
 * Reason: Composes helper mixins with complex nested hover states (.ant-input-password-icon:hover).
 * Multiple theme-aware color transitions difficult to manage in pure CSS.
 */
export const LargePasswordInput = styled(RediaccPasswordInput)`
  && {
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-size: ${({ theme }) => theme.fontSize.MD}px;
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

      .ant-input-password-icon {
        color: ${({ theme }) => theme.colors.textTertiary};
        font-size: ${({ theme }) => theme.fontSize.LG}px;
        cursor: pointer;
        padding: ${({ theme }) => theme.spacing.XS}px;

        &:hover {
          color: ${({ theme }) => theme.colors.textSecondary};
          background-color: ${({ theme }) => theme.colors.bgPrimary};
        }
      }
    }

    ${inputFocusStyles}
  }
`;

// ============================================
// LOADING COMPONENTS
// ============================================

export const LoadingContainer = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.XXXL}px 0;
`;

// ============================================
// MISC COMPONENTS
// ============================================

export const ModeSegmented = styled(Segmented)`
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
`;

export const LastFetchedText = styled.span.attrs({
  className: 'last-fetched-text',
})`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  white-space: nowrap;
`;

export const SectionMargin = styled.div.attrs({ className: 'section-margin' })<{
  $top?: number;
  $bottom?: number;
}>`
  ${({ $top }) => $top && `margin-top: ${$top}px;`}
  ${({ $bottom }) => $bottom && `margin-bottom: ${$bottom}px;`}
`;

export const InfoList = styled.ul.attrs({ className: 'info-list' })<{
  $top?: number;
  $bottom?: number;
}>`
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;
