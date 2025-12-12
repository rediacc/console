import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type {
  StackAlign,
  StackDirection,
  StackGap,
  StackJustify,
  StackVariant,
} from './RediaccStack.types';

// Resolve variant to direction, gap, and wrap
type VariantDefaults = { direction: StackDirection; gap: StackGap; wrap?: boolean };

/**
 * Variant defaults map
 */
const VARIANT_DEFAULTS_MAP: Record<StackVariant, VariantDefaults> = {
  default: { direction: 'horizontal', gap: 'md' },
  row: { direction: 'horizontal', gap: 'md' },
  column: { direction: 'vertical', gap: 'md' },
  'tight-row': { direction: 'horizontal', gap: 'xs' },
  'spaced-column': { direction: 'vertical', gap: 'lg' },
  'wrap-grid': { direction: 'horizontal', gap: 'sm', wrap: true },
};

export const resolveStackVariantDefaults = (variant: StackVariant = 'default'): VariantDefaults =>
  VARIANT_DEFAULTS_MAP[variant];

/**
 * Gap to spacing map
 */
const GAP_MAP: Record<StackGap, (theme: StyledTheme) => number> = {
  none: () => 0,
  xs: (theme) => theme.spacing.XS, // 4px
  sm: (theme) => theme.spacing.SM, // 8px
  md: (theme) => theme.spacing.MD, // 16px
  lg: (theme) => theme.spacing.LG, // 24px
  xl: (theme) => theme.spacing.XL, // 32px
};

// Resolve gap to pixels
export const resolveStackGap = (theme: StyledTheme, gap: StackGap | number = 'md'): number => {
  if (typeof gap === 'number') return gap;
  return GAP_MAP[gap](theme);
};

/**
 * Align to CSS align-items map
 */
const ALIGN_MAP: Record<StackAlign, string> = {
  start: 'flex-start',
  end: 'flex-end',
  center: 'center',
  baseline: 'baseline',
  stretch: 'stretch',
};

// Map align to CSS align-items
const mapAlign = (align: StackAlign = 'stretch'): string => ALIGN_MAP[align];

/**
 * Justify to CSS justify-content map
 */
const JUSTIFY_MAP: Record<StackJustify, string> = {
  start: 'flex-start',
  end: 'flex-end',
  center: 'center',
  between: 'space-between',
  around: 'space-around',
};

// Map justify to CSS justify-content
const mapJustify = (justify: StackJustify = 'start'): string => JUSTIFY_MAP[justify];

export const StyledRediaccStack = styled.div<{
  $direction: StackDirection;
  $gap: StackGap | number;
  $align: StackAlign;
  $justify: StackJustify;
  $wrap?: boolean;
  $fullWidth?: boolean;
}>`
  display: flex;
  flex-direction: ${({ $direction }) => ($direction === 'vertical' ? 'column' : 'row')};
  gap: ${({ theme, $gap }) => resolveStackGap(theme, $gap)}px;
  align-items: ${({ $align }) => mapAlign($align)};
  justify-content: ${({ $justify }) => mapJustify($justify)};

  ${({ $wrap }) => $wrap && css`flex-wrap: wrap;`}
  ${({ $fullWidth }) => $fullWidth && css`width: 100%;`}
`;
