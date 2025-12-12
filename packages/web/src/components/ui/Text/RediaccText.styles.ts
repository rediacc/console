import { Typography } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type {
  TextAlign,
  TextColor,
  TextElement,
  TextSize,
  TextVariant,
  TextWeight,
} from './RediaccText.types';

const { Text: AntText } = Typography;

type VariantTokenSet = {
  fontSize: number;
  fontWeight: number;
  color: string;
  lineHeight?: number;
  fontFamily?: string;
};

/**
 * Variant token map for text variants
 */
const VARIANT_TOKENS: Record<string, (theme: StyledTheme) => VariantTokenSet> = {
  caption: (theme) => ({
    fontSize: theme.fontSize.XS,
    fontWeight: theme.fontWeight.REGULAR,
    color: theme.colors.textSecondary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
  label: (theme) => ({
    fontSize: theme.fontSize.XS,
    fontWeight: theme.fontWeight.REGULAR,
    color: theme.colors.textSecondary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
  value: (theme) => ({
    fontSize: theme.fontSize.SM,
    fontWeight: theme.fontWeight.REGULAR,
    color: theme.colors.textPrimary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
  title: (theme) => ({
    fontSize: theme.fontSize.LG,
    fontWeight: theme.fontWeight.SEMIBOLD,
    color: theme.colors.textPrimary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
  description: (theme) => ({
    fontSize: theme.fontSize.SM,
    fontWeight: theme.fontWeight.REGULAR,
    color: theme.colors.textSecondary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
  helper: (theme) => ({
    fontSize: theme.fontSize.SM,
    fontWeight: theme.fontWeight.REGULAR,
    color: theme.colors.textSecondary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
  default: (theme) => ({
    fontSize: theme.fontSize.MD,
    fontWeight: theme.fontWeight.REGULAR,
    color: theme.colors.textPrimary,
    lineHeight: theme.lineHeight.NORMAL,
  }),
};

/**
 * Resolves theme tokens for each text variant
 */
export const resolveTextVariantTokens = (
  variant?: TextVariant,
  theme?: StyledTheme
): VariantTokenSet => {
  if (!theme) {
    throw new Error('Theme is required for resolveTextVariantTokens');
  }

  return VARIANT_TOKENS[variant ?? 'default'](theme);
};

/**
 * Size to font size map
 */
const SIZE_MAP: Record<TextSize, (theme: StyledTheme) => number> = {
  xs: (theme) => theme.fontSize.XS,
  sm: (theme) => theme.fontSize.SM,
  md: (theme) => theme.fontSize.MD,
  lg: (theme) => theme.fontSize.LG,
  xl: (theme) => theme.fontSize.XL,
};

/**
 * Resolves font size from size prop
 */
export const resolveTextSize = (theme: StyledTheme, size?: TextSize): number | undefined => {
  if (!size) return undefined;
  return SIZE_MAP[size](theme);
};

/**
 * Weight to font weight map
 */
const WEIGHT_MAP: Record<TextWeight, (theme: StyledTheme) => number> = {
  regular: (theme) => theme.fontWeight.REGULAR,
  medium: (theme) => theme.fontWeight.MEDIUM,
  semibold: (theme) => theme.fontWeight.SEMIBOLD,
  bold: (theme) => theme.fontWeight.BOLD,
};

/**
 * Resolves font weight from weight prop
 */
export const resolveTextWeight = (theme: StyledTheme, weight?: TextWeight): number | undefined => {
  if (!weight) return undefined;
  return WEIGHT_MAP[weight](theme);
};

/**
 * Color to theme color map
 */
const COLOR_MAP: Record<TextColor, (theme: StyledTheme) => string> = {
  primary: (theme) => theme.colors.textPrimary,
  secondary: (theme) => theme.colors.textSecondary,
  tertiary: (theme) => theme.colors.textTertiary,
  muted: (theme) => theme.colors.textMuted,
  danger: (theme) => theme.colors.error,
  success: (theme) => theme.colors.success,
  warning: (theme) => theme.colors.warning,
  info: (theme) => theme.colors.info,
  inherit: () => 'inherit',
};

/**
 * Resolves text color from color prop
 */
export const resolveTextColor = (theme: StyledTheme, color?: TextColor): string | undefined => {
  if (!color) return undefined;
  return COLOR_MAP[color](theme);
};

/**
 * Unified Text styled component
 */
export const StyledRediaccText = styled(AntText).withConfig({
  shouldForwardProp: (prop) =>
    ![
      '$variant',
      '$size',
      '$weight',
      '$color',
      '$align',
      '$truncate',
      '$maxLines',
      '$code',
      '$as',
    ].includes(prop),
})<{
  $variant?: TextVariant;
  $size?: TextSize;
  $weight?: TextWeight;
  $color?: TextColor;
  $align?: TextAlign;
  $truncate?: boolean;
  $maxLines?: number;
  $code?: boolean;
  $as?: TextElement;
}>`
  && {
    /* Reset default margin */
    margin: 0;

    /* Apply variant styling */
    font-size: ${({ theme, $variant }) => resolveTextVariantTokens($variant, theme).fontSize}px;
    font-weight: ${({ theme, $variant }) => resolveTextVariantTokens($variant, theme).fontWeight};
    color: ${({ theme, $variant }) => resolveTextVariantTokens($variant, theme).color};
    line-height: ${({ theme, $variant }) => resolveTextVariantTokens($variant, theme).lineHeight};
    ${({ theme, $variant }) => {
      const fontFamily = resolveTextVariantTokens($variant, theme).fontFamily;
      return fontFamily ? `font-family: ${fontFamily};` : '';
    }}

    /* Size override */
    ${({ theme, $size }) =>
      $size &&
      css`
        font-size: ${resolveTextSize(theme, $size)}px;
      `}

    /* Weight override */
    ${({ theme, $weight }) =>
      $weight &&
      css`
        font-weight: ${resolveTextWeight(theme, $weight)};
      `}

    /* Color override */
    ${({ theme, $color }) =>
      $color &&
      css`
        color: ${resolveTextColor(theme, $color)};
      `}

    /* Text alignment */
    ${({ $align }) =>
      $align &&
      css`
        text-align: ${$align};
      `}

    /* Code styling */
    ${({ $code, theme }) =>
      $code &&
      css`
        font-family: ${theme.fontFamily.MONO};
        font-size: ${theme.fontSize.SM}px;
        background-color: ${theme.colors.bgSecondary};
        padding: ${theme.spacing.XS}px ${theme.spacing.SM}px;
        border-radius: ${theme.borderRadius.SM}px;
        border: 1px solid ${theme.colors.borderSecondary};
      `}

    /* Truncation - single line */
    ${({ $truncate, $maxLines }) =>
      $truncate &&
      !$maxLines &&
      css`
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      `}

    /* Truncation - multi-line */
    ${({ $truncate, $maxLines }) =>
      $truncate &&
      $maxLines &&
      css`
        display: -webkit-box;
        -webkit-line-clamp: ${$maxLines};
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
      `}

    /* Display as block for certain elements */
    ${({ $as }) =>
      ($as === 'p' || $as === 'div') &&
      css`
        display: block;
      `}
  }
`;
