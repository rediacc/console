import styled, { css } from 'styled-components';
import { Typography } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type {
  TextVariant,
  TextSize,
  TextWeight,
  TextColor,
  TextAlign,
  TextElement,
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
 * Resolves theme tokens for each text variant
 */
export const resolveTextVariantTokens = (
  variant?: TextVariant,
  theme?: StyledTheme
): VariantTokenSet => {
  if (!theme) {
    throw new Error('Theme is required for resolveTextVariantTokens');
  }

  switch (variant) {
    case 'caption':
      return {
        fontSize: theme.fontSize.CAPTION,
        fontWeight: theme.fontWeight.REGULAR,
        color: theme.colors.textSecondary,
        lineHeight: theme.lineHeight.NORMAL,
      };
    default:
      // Default styling (previously 'body')
      return {
        fontSize: theme.fontSize.BASE,
        fontWeight: theme.fontWeight.REGULAR,
        color: theme.colors.textPrimary,
        lineHeight: theme.lineHeight.NORMAL,
      };
  }
};

/**
 * Resolves font size from size prop
 */
export const resolveTextSize = (theme: StyledTheme, size?: TextSize): number | undefined => {
  if (!size) return undefined;
  switch (size) {
    case 'xs':
      return theme.fontSize.XS;
    case 'sm':
      return theme.fontSize.SM;
    case 'md':
      return theme.fontSize.BASE;
    case 'lg':
      return theme.fontSize.LG;
    case 'xl':
      return theme.fontSize.XL;
    default:
      return undefined;
  }
};

/**
 * Resolves font weight from weight prop
 */
export const resolveTextWeight = (
  theme: StyledTheme,
  weight?: TextWeight
): number | undefined => {
  if (!weight) return undefined;
  switch (weight) {
    case 'regular':
      return theme.fontWeight.REGULAR;
    case 'medium':
      return theme.fontWeight.MEDIUM;
    case 'semibold':
      return theme.fontWeight.SEMIBOLD;
    case 'bold':
      return 700;
    default:
      return undefined;
  }
};

/**
 * Resolves text color from color prop
 */
export const resolveTextColor = (theme: StyledTheme, color?: TextColor): string | undefined => {
  if (!color) return undefined;
  switch (color) {
    case 'primary':
      return theme.colors.textPrimary;
    case 'secondary':
      return theme.colors.textSecondary;
    case 'tertiary':
      return theme.colors.textTertiary;
    case 'muted':
      return theme.colors.textMuted;
    case 'danger':
      return theme.colors.error;
    case 'success':
      return theme.colors.success;
    case 'warning':
      return theme.colors.warning;
    case 'info':
      return theme.colors.info;
    case 'inherit':
      return 'inherit';
    default:
      return undefined;
  }
};

/**
 * Unified Text styled component
 */
export const StyledRediaccText = styled(AntText).withConfig({
  shouldForwardProp: (prop) =>
    !['$variant', '$size', '$weight', '$color', '$align', '$truncate', '$maxLines', '$code', '$as'].includes(
      prop
    ),
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
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
        font-size: ${theme.fontSize.SM}px;
        background-color: ${theme.colors.bgSecondary};
        padding: 2px 6px;
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
