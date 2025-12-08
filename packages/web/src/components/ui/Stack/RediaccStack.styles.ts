import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type {
  StackDirection,
  StackGap,
  StackAlign,
  StackJustify,
  StackVariant,
} from './RediaccStack.types';

// Resolve variant to direction, gap, and wrap
type VariantDefaults = { direction: StackDirection; gap: StackGap; wrap?: boolean };

export const resolveStackVariantDefaults = (variant: StackVariant = 'default'): VariantDefaults => {
  switch (variant) {
    case 'row':
      return { direction: 'horizontal', gap: 'md' };
    case 'column':
      return { direction: 'vertical', gap: 'md' };
    case 'tight-row':
      return { direction: 'horizontal', gap: 'xs' };
    case 'spaced-column':
      return { direction: 'vertical', gap: 'lg' };
    case 'wrap-grid':
      return { direction: 'horizontal', gap: 'sm', wrap: true };
    case 'default':
    default:
      return { direction: 'horizontal', gap: 'md' };
  }
};

// Resolve gap to pixels
export const resolveStackGap = (theme: StyledTheme, gap: StackGap | number = 'md'): number => {
  if (typeof gap === 'number') return gap;

  switch (gap) {
    case 'none':
      return 0;
    case 'xs':
      return theme.spacing.XS; // 4px
    case 'sm':
      return theme.spacing.SM; // 8px
    case 'lg':
      return theme.spacing.LG; // 24px
    case 'xl':
      return theme.spacing.XL; // 32px
    case 'md':
    default:
      return theme.spacing.MD; // 16px
  }
};

// Map align to CSS align-items
const mapAlign = (align: StackAlign = 'stretch'): string => {
  switch (align) {
    case 'start':
      return 'flex-start';
    case 'end':
      return 'flex-end';
    case 'center':
      return 'center';
    case 'baseline':
      return 'baseline';
    case 'stretch':
    default:
      return 'stretch';
  }
};

// Map justify to CSS justify-content
const mapJustify = (justify: StackJustify = 'start'): string => {
  switch (justify) {
    case 'end':
      return 'flex-end';
    case 'center':
      return 'center';
    case 'between':
      return 'space-between';
    case 'around':
      return 'space-around';
    case 'start':
    default:
      return 'flex-start';
  }
};

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
