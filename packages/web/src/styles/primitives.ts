import styled, { css, keyframes } from 'styled-components';
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
  Segmented,
  Row,
} from 'antd';
import type { TableProps } from 'antd';
import type { ComponentType } from 'react';
import type { StyledTheme } from '@/styles/styledTheme';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { RightOutlined } from '@/utils/optimizedIcons';

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

export const pulseAnimation = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
`;

// ============================================
// SHARED CSS HELPERS
// ============================================

export const scrollbarStyles = css`
  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: 4px;
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
    margin-left: 14px;
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
    margin-right: 14px;
  }

  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
    color: ${({ theme }) => theme.colors.primary};
  }
`;

const { Text } = Typography;
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
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';
export type ButtonSize = 'SM' | 'MD' | 'LG';
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

type TagTokenSet = { bg: string; color: string; border: string };
type TagTokenKeySet = { bg: ColorKey; color: ColorKey; border: ColorKey };

const TAG_TOKEN_KEYS: Record<TagVariant, TagTokenKeySet> = {
  primary: { bg: 'primaryBg', color: 'primary', border: 'primary' },
  secondary: { bg: 'bgPrimary', color: 'secondary', border: 'secondary' },
  success: { bg: 'bgSuccess', color: 'success', border: 'success' },
  warning: { bg: 'bgWarning', color: 'warning', border: 'warning' },
  error: { bg: 'bgError', color: 'error', border: 'error' },
  info: { bg: 'bgInfo', color: 'info', border: 'info' },
  neutral: { bg: 'bgSecondary', color: 'textSecondary', border: 'borderSecondary' },
  team: { bg: 'bgPrimary', color: 'success', border: 'success' },
  cluster: { bg: 'primaryBg', color: 'primary', border: 'primary' },
  vault: { bg: 'bgSecondary', color: 'textPrimary', border: 'borderSecondary' },
  machine: { bg: 'bgPrimary', color: 'primary', border: 'borderSecondary' },
  bridge: { bg: 'bgPrimary', color: 'secondary', border: 'secondary' },
  available: { bg: 'bgSuccess', color: 'success', border: 'success' },
  processing: { bg: 'primaryBg', color: 'primary', border: 'primary' },
};

const resolveTagVariantTokens = (
  variant: TagVariant = 'neutral',
  theme: StyledTheme
): TagTokenSet => {
  const tokens = TAG_TOKEN_KEYS[variant] || TAG_TOKEN_KEYS.neutral;
  return {
    bg: theme.colors[tokens.bg],
    color: theme.colors[tokens.color],
    border: theme.colors[tokens.border],
  };
};

const resolveTagPadding = (theme: StyledTheme, size: TagSize = 'SM') =>
  size === 'MD' ? `${theme.spacing.XS}px ${theme.spacing.SM}px` : `0 ${theme.spacing.XS}px`;

const resolveTagRadius = (theme: StyledTheme, size: TagSize = 'SM') =>
  size === 'MD' ? theme.borderRadius.MD : theme.borderRadius.SM;

const resolveTagFontSize = (theme: StyledTheme, size: TagSize = 'SM') =>
  size === 'MD' ? theme.fontSize.SM : theme.fontSize.CAPTION;

type ButtonTokenSet = {
  bg: string;
  color: string;
  border: string;
  hoverBg: string;
  hoverColor: string;
  hoverBorder: string;
};

const resolveButtonVariantTokens = (
  variant: ButtonVariant = 'secondary',
  theme: StyledTheme
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
      };
    case 'danger':
      return {
        bg: theme.colors.error,
        color: theme.colors.textInverse,
        border: theme.colors.error,
        hoverBg: theme.colors.error,
        hoverColor: theme.colors.textInverse,
        hoverBorder: theme.colors.error,
      };
    case 'ghost':
      return {
        bg: 'transparent',
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: theme.colors.borderSecondary,
      };
    case 'link':
      return {
        bg: 'transparent',
        color: theme.colors.primary,
        border: 'transparent',
        hoverBg: 'transparent',
        hoverColor: theme.colors.primaryHover,
        hoverBorder: 'transparent',
      };
    case 'secondary':
    default:
      return {
        bg: theme.colors.bgPrimary,
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: theme.colors.borderPrimary,
      };
  }
};

const resolveButtonHeight = (theme: StyledTheme, size: ButtonSize = 'MD') => {
  switch (size) {
    case 'SM':
      return theme.dimensions.CONTROL_HEIGHT_SM;
    case 'LG':
      return theme.dimensions.CONTROL_HEIGHT_LG;
    case 'MD':
    default:
      return theme.dimensions.CONTROL_HEIGHT;
  }
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

const fullWidthControlStyles = css`
  width: 100%;
`;

const PasswordInput = Input.Password;
const TextAreaInput = Input.TextArea;

export const PageContainer = styled.div.attrs({ className: 'page-container' })`
  width: 100%;
`;

const BasePageCard = styled(Card).attrs({ className: 'page-card' })``;

export const PageCard = BasePageCard;
export const FilterCard = BasePageCard;
export const TableCard = BasePageCard;
export const SectionCard = BasePageCard;

// ============================================
// TABLE PRIMITIVES
// ============================================

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
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
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

export const FiltersCard = styled(Card)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`;

export const FiltersGrid = styled(Space).attrs({ size: 8, wrap: true })`
  width: 100%;
`;

export const FilterSelect = styled(Select)<{ $minWidth?: number }>`
  min-width: ${({ $minWidth }) => ($minWidth ? `${$minWidth}px` : '150px')};
`;

export const FilterRangePicker = styled(DatePicker.RangePicker)`
  min-width: 220px;
`;

export const FilterInput = styled(Input)`
  min-width: 200px;
`;

export const FilterCheckbox = styled(Checkbox)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

// ============================================
// STATS COMPONENTS
// ============================================

export const StatsBar = styled(Space).attrs({ size: 12 })`
  align-items: center;
  flex-wrap: wrap;
`;

export const StatItem = styled(Space).attrs({ size: 4 })`
  align-items: center;
`;

export const StatLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const StatValue = styled(Text)<{ $color?: string }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ $color, theme }) => $color || theme.colors.textPrimary};
  }
`;

export const StatDivider = styled.span`
  display: inline-block;
  width: 1px;
  height: 16px;
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

export const TabCount = styled(Badge)<{ $color?: string }>`
  .ant-scroll-number {
    background-color: ${({ $color, theme }) => $color || theme.colors.primary};
  }
`;

// ============================================
// EMPTY STATE COMPONENTS
// ============================================

export const PaddedEmpty = styled(Empty)`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
`;

export const EmptyStateWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
  text-align: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const EmptyStatePanel = styled(PaddedEmpty)<{
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

const ButtonSurface = styled(Button)<{
  $variant?: ButtonVariant;
  $size?: ButtonSize;
  $minWidth?: number;
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
`;

export const PrimaryButton = styled(ButtonSurface).attrs({
  $variant: 'primary',
})``;

export const SecondaryButton = styled(ButtonSurface).attrs({
  $variant: 'secondary',
})``;

export const ActionButton = styled(ButtonSurface).attrs({
  $variant: 'secondary',
})`
  && {
    min-width: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT}px;
  }
`;

export const CardTitle = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.H4}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const HelperText = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const CaptionText = styled(Text)<{ $muted?: boolean; $size?: number }>`
  && {
    margin: 0;
    font-size: ${({ theme, $size }) =>
      $size !== undefined ? `${$size}px` : `${theme.fontSize.CAPTION}px`};
    color: ${({ theme, $muted }) => ($muted ? theme.colors.textSecondary : theme.colors.textPrimary)};
  }
`;

export const MutedCaption = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const EmptyStateTitle = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const EmptyStateDescription = styled(Text)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const FormLabel = styled(Text)`
  && {
    margin: 0;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const ContentSection = styled.div`
  min-height: 400px;
`;

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
`;

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
`;

export const PillTag = styled(Tag)<{
  $variant?: TagVariant;
  $size?: TagSize;
  $borderless?: boolean;
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
`;

export const CompactIconButton = styled(IconButton)`
  width: ${({ theme }) => theme.spacing.XXL}px;
  height: ${({ theme }) => theme.spacing.XXL}px;
  min-width: ${({ theme }) => theme.spacing.XXL}px;
  min-height: ${({ theme }) => theme.spacing.XXL}px;
`;

export const PrimaryIconButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing.XXXL}px;
  min-height: ${({ theme }) => theme.spacing.XXXL}px;
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
`;

export const SecondaryIconButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing.XXXL}px;
  min-height: ${({ theme }) => theme.spacing.XXXL}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`;

export const CompactButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing.XXL}px;
  min-height: ${({ theme }) => theme.spacing.XXL}px;
`;

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
// FORM CONTROL PRIMITIVES
// ============================================

export const FullWidthInput = styled(Input)`
  && {
    ${fullWidthControlStyles};
  }
`;

export const FullWidthPasswordInput = styled(PasswordInput)`
  && {
    ${fullWidthControlStyles};
  }
`;

export const FullWidthTextArea = styled(TextAreaInput)`
  && {
    ${fullWidthControlStyles};
  }
`;

export const FullWidthInputNumber = styled(InputNumber)`
  && {
    ${fullWidthControlStyles};
  }
`;

export const FullWidthSelect = styled(Select)`
  && {
    ${fullWidthControlStyles};
  }
`;

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
`;

export const BaseTable = styled(GenericTable)<{ $isInteractive?: boolean }>`
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
`;

// ============================================
// ADDITIONAL CARD VARIANTS
// ============================================

export const ContentCard = styled(Card)`
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

export const SelectableCard = styled(Card)<{
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

export const SpacedCard = styled(Card)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

// ============================================
// ADDITIONAL TEXT VARIANTS
// ============================================

export const TitleText = styled(Text)<{ $level?: 1 | 2 | 3 | 4 | 5 }>`
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
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
  }
`;

export const SecondaryText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const DescriptionText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
    line-height: ${({ theme }) => theme.lineHeight.RELAXED};
  }
`;

export const MonoText = styled(Text)`
  && {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ItalicText = styled(Text)`
  && {
    font-style: italic;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const NoMarginTitle = styled(Typography.Title)`
  && {
    margin: 0;
  }
`;

// ============================================
// ADDITIONAL BUTTON VARIANTS
// ============================================

export const SubmitButton = styled(PrimaryButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

export const LargeSubmitButton = styled(PrimaryButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
  }
`;

export const SmallActionButton = styled(ActionButton)`
  && {
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
  }
`;

export const CreateButton = styled(PrimaryButton)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
  }
`;

export const GhostButton = styled(ButtonSurface).attrs({ $variant: 'ghost' })``;

export const LinkButton = styled(ButtonSurface).attrs({ $variant: 'link' })``;

export const DangerButton = styled(ButtonSurface).attrs({ $variant: 'danger' })``;

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

export const ContentStack = styled(FlexColumn).attrs({ $gap: 'MD' })``;

export const HeaderRow = styled(FlexRow).attrs({ $justify: 'space-between', $wrap: true })`
  width: 100%;
`;

export const CenteredContent = styled.div`
  text-align: center;
`;

export const CenteredRow = styled(Row)`
  text-align: center;
`;

export const FullWidthSpace = styled(Space)`
  width: 100%;
`;

// ============================================
// SCROLLABLE CONTAINERS
// ============================================

export const ScrollContainer = styled.div<{ $maxHeight?: number }>`
  max-height: ${({ $maxHeight }) => ($maxHeight ? `${$maxHeight}px` : '400px')};
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
  height: ${({ $height }) => ($height ? `${$height}px` : '400px')};
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
    max-width: 1200px;
    width: 1200px;
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

export const LargeInput = styled(Input)`
  && {
    height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    &.ant-input-affix-wrapper {
      padding: 0;
    }

    input.ant-input {
      padding: 0 14px;
      height: 100%;
    }

    ${inputPrefixStyles}
    ${inputFocusStyles}
  }
`;

export const LargePasswordInput = styled(Input.Password)`
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
      padding: 0 14px;
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
        padding: 4px;
        border-radius: 4px;

        &:hover {
          color: ${({ theme }) => theme.colors.textSecondary};
          background-color: ${({ theme }) => theme.colors.bgHover};
        }
      }
    }

    ${inputFocusStyles}
  }
`;

export const SearchInput = styled(Input.Search)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

// ============================================
// ALERT VARIANTS
// ============================================

export const SpacedAlert = styled(Alert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const RoundedAlert = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ErrorAlert = styled(AlertCard).attrs({ $variant: 'error' })``;

export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })``;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;

// ============================================
// TAG VARIANTS
// ============================================

export const SmallTag = styled(PillTag).attrs({ $size: 'SM' })``;

export const StatusTagSmall = styled(StatusTag)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    line-height: 1.2;
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
