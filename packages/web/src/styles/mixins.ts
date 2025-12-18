import { css, RuleSet, Interpolation } from 'styled-components';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

/**
 * Disabled state mixin - consistent disabled styling for form controls
 * Note: No visual styling per user requirement - functional blocking only
 */
export const disabledState = css`
  cursor: not-allowed;
  pointer-events: none;
`;

/**
 * Focus ring mixin - accessible focus indicators
 * @param style - 'outline' for visible outline, 'shadow' for box-shadow ring
 */
export const focusRing = (style: 'outline' | 'shadow' = 'shadow') =>
  style === 'outline'
    ? css`
        outline: 2px solid ${({ theme }) => theme.colors.primary};
        outline-offset: 2px;
      `
    : css`
        outline: none;
      `;

type MediaQueryFn = (
  strings: TemplateStringsArray,
  ...values: Interpolation<object>[]
) => RuleSet<object>;

/**
 * Media query helpers for responsive design
 * Usage: ${media.mobile`display: none;`}
 *        ${media.tabletUp`padding: 24px;`}
 */
export const media: Record<string, MediaQueryFn> = {
  // Max-width queries (at or below breakpoint)
  mobile: (strings, ...values) =>
    css`
      @media (max-width: ${DESIGN_TOKENS.BREAKPOINTS.MOBILE}px) {
        ${css(strings, ...values)}
      }
    `,

  tablet: (strings, ...values) =>
    css`
      @media (max-width: ${DESIGN_TOKENS.BREAKPOINTS.TABLET}px) {
        ${css(strings, ...values)}
      }
    `,

  desktop: (strings, ...values) =>
    css`
      @media (max-width: ${DESIGN_TOKENS.BREAKPOINTS.DESKTOP}px) {
        ${css(strings, ...values)}
      }
    `,

  wide: (strings, ...values) =>
    css`
      @media (max-width: ${DESIGN_TOKENS.BREAKPOINTS.WIDE}px) {
        ${css(strings, ...values)}
      }
    `,

  // Min-width queries (above breakpoint)
  mobileUp: (strings, ...values) =>
    css`
      @media (min-width: ${DESIGN_TOKENS.BREAKPOINTS.MOBILE + 1}px) {
        ${css(strings, ...values)}
      }
    `,

  tabletUp: (strings, ...values) =>
    css`
      @media (min-width: ${DESIGN_TOKENS.BREAKPOINTS.TABLET + 1}px) {
        ${css(strings, ...values)}
      }
    `,

  desktopUp: (strings, ...values) =>
    css`
      @media (min-width: ${DESIGN_TOKENS.BREAKPOINTS.DESKTOP + 1}px) {
        ${css(strings, ...values)}
      }
    `,

  wideUp: (strings, ...values) =>
    css`
      @media (min-width: ${DESIGN_TOKENS.BREAKPOINTS.WIDE + 1}px) {
        ${css(strings, ...values)}
      }
    `,
};
