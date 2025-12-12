import { Card as AntCard } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { CardSize, CardSpacing, CardVariant } from './RediaccCard.types';

const CARD_SPACING_MAP: Record<CardSpacing, keyof StyledTheme['spacing'] | 0> = {
  compact: 'SM',
  default: 'MD',
  spacious: 'LG',
  none: 0,
};

// Resolve spacing to margin-bottom pixels
export const resolveCardSpacing = (theme: StyledTheme, spacing?: CardSpacing): number => {
  if (!spacing) return 0;
  const value = CARD_SPACING_MAP[spacing];
  return typeof value === 'number' ? value : theme.spacing[value];
};

const CARD_PADDING_MAP: Record<CardSize, keyof StyledTheme['spacing']> = {
  sm: 'SM_LG',
  md: 'MD',
  lg: 'LG',
};

// Resolve padding based on size
export const resolveCardPadding = (theme: StyledTheme, size: CardSize = 'md'): number => {
  return theme.spacing[CARD_PADDING_MAP[size] || CARD_PADDING_MAP.md];
};

// Token set for card variants
type CardTokenSet = { bg: string; border: string; shadow: string };

type CardTokenKeys = {
  bg: keyof StyledTheme['colors'];
  border: keyof StyledTheme['colors'] | 'transparent';
  shadow: keyof StyledTheme['shadows'] | 'none';
};

const CARD_VARIANT_MAP: Record<CardVariant, CardTokenKeys> = {
  elevated: { bg: 'bgPrimary', border: 'transparent', shadow: 'CARD' },
  bordered: { bg: 'bgPrimary', border: 'borderSecondary', shadow: 'none' },
  section: { bg: 'bgSecondary', border: 'borderSecondary', shadow: 'none' },
  selectable: { bg: 'bgPrimary', border: 'borderSecondary', shadow: 'none' },
  default: { bg: 'bgPrimary', border: 'borderSecondary', shadow: 'none' },
};

export const resolveCardVariantTokens = (
  variant: CardVariant = 'default',
  theme: StyledTheme
): CardTokenSet => {
  const keys = CARD_VARIANT_MAP[variant] || CARD_VARIANT_MAP.default;
  return {
    bg: theme.colors[keys.bg],
    border: keys.border === 'transparent' ? 'transparent' : theme.colors[keys.border],
    shadow: keys.shadow === 'none' ? 'none' : theme.shadows[keys.shadow],
  };
};

export const StyledRediaccCard = styled(AntCard)<{
  $variant: CardVariant;
  $size: CardSize;
  $selected?: boolean;
  $interactive?: boolean;
  $fullWidth?: boolean;
  $fullHeight?: boolean;
  $spacing?: CardSpacing;
  $noPadding?: boolean;
}>`
  && {
    background-color: ${({ theme, $variant }) => resolveCardVariantTokens($variant, theme).bg};
    border: 1px solid ${({ theme, $variant, $selected }) =>
      $selected ? theme.colors.primary : resolveCardVariantTokens($variant, theme).border};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme, $variant }) => resolveCardVariantTokens($variant, theme).shadow};

    /* Spacing (margin-bottom) */
    ${({ theme, $spacing }) => $spacing && css`margin-bottom: ${resolveCardSpacing(theme, $spacing)}px;`}

    /* Width */
    ${({ $fullWidth }) => $fullWidth && css`width: 100%;`}

    /* Height */
    ${({ $fullHeight }) => $fullHeight && css`height: 100%;`}

    /* Padding */
    .ant-card-body {
      padding: ${({ theme, $size, $noPadding }) =>
        $noPadding ? '0' : `${resolveCardPadding(theme, $size)}px`};
    }

    /* Selected state for selectable variant */
    ${({ $selected, theme }) =>
      $selected &&
      css`
      border-width: 2px;
      border-color: ${theme.colors.primary};
    `}

    /* Interactive hover effects */
    ${({ $interactive, theme }) =>
      $interactive &&
      css`
      cursor: pointer;
      transition: ${theme.transitions.HOVER};

      &:hover {
        border-color: ${theme.colors.primary};
        box-shadow: ${theme.shadows.SM};
      }
    `}
  }
`;
