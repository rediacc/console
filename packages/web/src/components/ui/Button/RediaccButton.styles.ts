import { Button as AntButton } from 'antd';
import styled, { css } from 'styled-components';
import { disabledState } from '@/styles/mixins';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ButtonVariant } from './RediaccButton.types';

type ButtonTokenSet = {
  bg: string;
  color: string;
  border: string;
  hoverBg: string;
  hoverColor: string;
  hoverBorder: string;
};

/**
 * Variant token map for button variants
 * Variants: primary, danger, default, text, link, ghost
 */
const VARIANT_TOKENS: Record<ButtonVariant, (theme: StyledTheme) => ButtonTokenSet> = {
  primary: (theme) => ({
    bg: theme.colors.buttonPrimary,
    color: theme.colors.buttonPrimaryText,
    border: theme.colors.buttonPrimary,
    hoverBg: theme.colors.buttonPrimaryHover,
    hoverColor: theme.colors.buttonPrimaryText,
    hoverBorder: theme.colors.buttonPrimaryHover,
  }),
  danger: (theme) => ({
    bg: theme.colors.error,
    color: theme.colors.textInverse,
    border: theme.colors.error,
    hoverBg: theme.colors.error,
    hoverColor: theme.colors.textInverse,
    hoverBorder: theme.colors.error,
  }),
  default: (theme) => ({
    bg: theme.colors.bgPrimary,
    color: theme.colors.textPrimary,
    border: theme.colors.borderSecondary,
    hoverBg: theme.colors.bgPrimary,
    hoverColor: theme.colors.textPrimary,
    hoverBorder: theme.colors.borderPrimary,
  }),
  text: (theme) => ({
    bg: 'transparent',
    color: theme.colors.textPrimary,
    border: 'transparent',
    hoverBg: theme.colors.bgPrimary,
    hoverColor: theme.colors.textPrimary,
    hoverBorder: theme.colors.borderPrimary,
  }),
  link: (theme) => ({
    bg: 'transparent',
    color: theme.colors.primary,
    border: 'transparent',
    hoverBg: 'transparent',
    hoverColor: theme.colors.primaryHover,
    hoverBorder: 'transparent',
  }),
  ghost: (theme) => ({
    bg: 'transparent',
    color: theme.colors.textPrimary,
    border: theme.colors.borderSecondary,
    hoverBg: theme.colors.bgPrimary,
    hoverColor: theme.colors.textPrimary,
    hoverBorder: theme.colors.borderPrimary,
  }),
};

/**
 * Resolves color tokens for each button variant
 */
export const resolveRediaccButtonVariantTokens = (
  theme: StyledTheme,
  variant: ButtonVariant = 'primary'
): ButtonTokenSet => VARIANT_TOKENS[variant](theme);

/**
 * Unified Button styled component
 */
export const StyledRediaccButton = styled(AntButton)<{
  $variant: ButtonVariant;
  $iconOnly: boolean;
  $minWidth?: number;
  $fullWidth?: boolean;
}>`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};

    /* Icon-only mode - square button */
    ${({ $iconOnly, theme }) =>
      $iconOnly &&
      css`
        width: ${theme.dimensions.FORM_CONTROL_HEIGHT}px;
        min-width: ${theme.dimensions.FORM_CONTROL_HEIGHT}px;
        padding: 0;
      `}

    /* Text button padding */
    ${({ $iconOnly, theme }) =>
      !$iconOnly &&
      css`
        padding: 0 ${theme.spacing.MD}px;
      `}

    /* Width modifiers */
    ${({ $minWidth }) =>
      $minWidth &&
      css`
        min-width: ${$minWidth}px;
      `}

    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Link variant underline on hover */
    ${({ $variant }) =>
      $variant === 'link' &&
      css`
        &:not(:disabled):hover {
          text-decoration: underline;
        }
      `}

    /* Disabled state */
    &:disabled {
      ${disabledState}
    }
  }
`;
