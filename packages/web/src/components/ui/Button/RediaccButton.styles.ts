import { Button as AntButton } from 'antd';
import styled, { css } from 'styled-components';
import { disabledState } from '@/styles/mixins';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ButtonSize, ButtonVariant } from './RediaccButton.types';

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
    hoverBg: theme.colors.bgSecondary,
    hoverColor: theme.colors.textPrimary,
    hoverBorder: theme.colors.borderPrimary,
  }),
  text: (theme) => ({
    bg: 'transparent',
    color: theme.colors.textPrimary,
    border: 'transparent',
    hoverBg: theme.colors.bgSecondary,
    hoverColor: theme.colors.textPrimary,
    hoverBorder: 'transparent',
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
    hoverBg: theme.colors.bgSecondary,
    hoverColor: theme.colors.textPrimary,
    hoverBorder: theme.colors.borderPrimary,
  }),
};

/**
 * Resolves color tokens for each button variant
 */
export const resolveRediaccButtonVariantTokens = (
  variant: ButtonVariant = 'primary',
  theme: StyledTheme
): ButtonTokenSet => VARIANT_TOKENS[variant](theme);

/**
 * Button height map by size
 */
const SIZE_HEIGHT_MAP: Record<ButtonSize, (theme: StyledTheme) => number> = {
  sm: (theme) => theme.dimensions.CONTROL_HEIGHT_SM, // 28px
  md: (theme) => theme.dimensions.CONTROL_HEIGHT, // 32px
};

/**
 * Resolves height for each button size
 */
export const resolveRediaccButtonHeight = (theme: StyledTheme, size: ButtonSize = 'md'): number =>
  SIZE_HEIGHT_MAP[size](theme);

/**
 * Unified Button styled component
 */
export const StyledRediaccButton = styled(AntButton)<{
  $variant: ButtonVariant;
  $size: ButtonSize;
  $iconOnly: boolean;
  $minWidth?: number;
  $fullWidth?: boolean;
}>`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    min-height: ${({ theme, $size }) => resolveRediaccButtonHeight(theme, $size)}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    transition: ${({ theme }) => theme.transitions.BUTTON};

    /* Variant-specific colors */
    background-color: ${({ theme, $variant }) => resolveRediaccButtonVariantTokens($variant, theme).bg};
    color: ${({ theme, $variant }) => resolveRediaccButtonVariantTokens($variant, theme).color};
    border: 1px solid ${({ theme, $variant }) => resolveRediaccButtonVariantTokens($variant, theme).border};

    /* Icon-only mode - square button */
    ${({ $iconOnly, theme, $size }) =>
      $iconOnly &&
      css`
        width: ${resolveRediaccButtonHeight(theme, $size)}px;
        min-width: ${resolveRediaccButtonHeight(theme, $size)}px;
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

    /* Hover/focus states */
    &:not(:disabled):hover,
    &:not(:disabled):focus {
      background-color: ${({ theme, $variant }) =>
        resolveRediaccButtonVariantTokens($variant, theme).hoverBg};
      color: ${({ theme, $variant }) => resolveRediaccButtonVariantTokens($variant, theme).hoverColor};
      border-color: ${({ theme, $variant }) =>
        resolveRediaccButtonVariantTokens($variant, theme).hoverBorder};
    }

    /* Solid button hover effects (not for text/link variants) */
    ${({ $variant }) =>
      $variant !== 'text' &&
      $variant !== 'link' &&
      css`
        &:not(:disabled):hover,
        &:not(:disabled):focus {
          transform: translateY(-1px);
          box-shadow: ${({ theme }) => theme.shadows.BUTTON_HOVER};
        }
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
