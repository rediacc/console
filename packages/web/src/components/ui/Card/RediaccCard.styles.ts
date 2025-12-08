import { Card as AntCard } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { CardSize, CardSpacing, CardVariant } from './RediaccCard.types';

// Resolve spacing to margin-bottom pixels
export const resolveCardSpacing = (theme: StyledTheme, spacing?: CardSpacing): number => {
  switch (spacing) {
    case 'compact':
      return theme.spacing.SM; // 8px
    case 'default':
      return theme.spacing.MD; // 16px
    case 'spacious':
      return theme.spacing.LG; // 24px
    case 'none':
    default:
      return 0;
  }
};

// Resolve padding based on size
export const resolveCardPadding = (theme: StyledTheme, size: CardSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.spacing.SM_LG; // 12px
    case 'lg':
      return theme.spacing.LG; // 24px
    case 'md':
    default:
      return theme.spacing.MD; // 16px
  }
};

// Token set for card variants
type CardTokenSet = { bg: string; border: string; shadow: string };

export const resolveCardVariantTokens = (
  variant: CardVariant = 'default',
  theme: StyledTheme
): CardTokenSet => {
  switch (variant) {
    case 'elevated':
      return { bg: theme.colors.bgPrimary, border: 'transparent', shadow: theme.shadows.CARD };
    case 'bordered':
      return { bg: theme.colors.bgPrimary, border: theme.colors.borderSecondary, shadow: 'none' };
    case 'section':
      return { bg: theme.colors.bgSecondary, border: theme.colors.borderSecondary, shadow: 'none' };
    case 'selectable':
      return { bg: theme.colors.bgPrimary, border: theme.colors.borderSecondary, shadow: 'none' };
    case 'default':
    default:
      return { bg: theme.colors.bgPrimary, border: theme.colors.borderSecondary, shadow: 'none' };
  }
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
