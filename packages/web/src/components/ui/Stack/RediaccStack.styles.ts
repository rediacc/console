import styled, { css } from 'styled-components';
import type { StackAlign, StackDirection, StackJustify, StackVariant } from './RediaccStack.types';

// Resolve variant to direction and wrap
type VariantDefaults = { direction: StackDirection; wrap?: boolean };

/**
 * Variant defaults map
 */
const VARIANT_DEFAULTS_MAP: Record<StackVariant, VariantDefaults> = {
  default: { direction: 'horizontal' },
  row: { direction: 'horizontal' },
  column: { direction: 'vertical' },
  'tight-row': { direction: 'horizontal' },
  'spaced-column': { direction: 'vertical' },
  'wrap-grid': { direction: 'horizontal', wrap: true },
};

export const resolveStackVariantDefaults = (variant: StackVariant = 'default'): VariantDefaults =>
  VARIANT_DEFAULTS_MAP[variant];

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
  $align: StackAlign;
  $justify: StackJustify;
  $wrap?: boolean;
  $fullWidth?: boolean;
}>`
  display: flex;
  flex-direction: ${({ $direction }) => ($direction === 'vertical' ? 'column' : 'row')};
  align-items: ${({ $align }) => mapAlign($align)};
  justify-content: ${({ $justify }) => mapJustify($justify)};

  ${({ $wrap }) => $wrap && css`flex-wrap: wrap;`}
  ${({ $fullWidth }) => $fullWidth && css`width: 100%;`}
`;
