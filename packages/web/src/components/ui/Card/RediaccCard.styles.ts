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
type CardTokenSet = { bg: string; border: string };

type CardTokenKeys = {
  bg: keyof StyledTheme['colors'];
  border: keyof StyledTheme['colors'] | 'transparent';
};

const CARD_VARIANT_MAP: Record<CardVariant, CardTokenKeys> = {
  elevated: { bg: 'bgPrimary', border: 'transparent' },
  bordered: { bg: 'bgPrimary', border: 'borderSecondary' },
  section: { bg: 'bgPrimary', border: 'borderPrimary' },
  selectable: { bg: 'bgPrimary', border: 'borderSecondary' },
  default: { bg: 'bgPrimary', border: 'borderSecondary' },
};

export const resolveCardVariantTokens = (
  variant: CardVariant = 'default',
  theme: StyledTheme
): CardTokenSet => {
  const keys = CARD_VARIANT_MAP[variant] || CARD_VARIANT_MAP.default;
  return {
    bg: theme.colors[keys.bg],
    border: keys.border === 'transparent' ? 'transparent' : theme.colors[keys.border],
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
    ${({ $selected }) =>
      $selected &&
      css`
    `}

    /* Interactive hover effects */
    ${({ $interactive }) =>
      $interactive &&
      css`
      cursor: pointer;
    `}
  }
`;
