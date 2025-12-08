import { css } from 'styled-components';

/**
 * Bordered card mixin - applies consistent border and border-radius
 * @param borderColor - 'borderSecondary' or 'borderPrimary'
 * @param radius - 'SM', 'MD', 'LG', or 'XL'
 */
export const borderedCard = (
  borderColor: 'borderSecondary' | 'borderPrimary' = 'borderSecondary',
  radius: 'SM' | 'MD' | 'LG' | 'XL' = 'LG'
) => css`
  border: 1px solid ${({ theme }) => theme.colors[borderColor]};
  border-radius: ${({ theme }) => theme.borderRadius[radius]}px;
`;

/**
 * Disabled state mixin - consistent disabled styling for form controls
 */
export const disabledState = css`
  cursor: not-allowed;
  opacity: 0.6;
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
        box-shadow: 0 0 0 2px ${({ theme }) => theme.colors.primaryBg};
      `;
