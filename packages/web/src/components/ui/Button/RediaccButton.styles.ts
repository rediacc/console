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
 * Resolves color tokens for each button variant
 * Variants: primary, danger, default, text, link, ghost
 */
export const resolveRediaccButtonVariantTokens = (
  variant: ButtonVariant = 'primary',
  theme: StyledTheme
): ButtonTokenSet => {
  switch (variant) {
    case 'danger':
      return {
        bg: theme.colors.error,
        color: theme.colors.textInverse,
        border: theme.colors.error,
        hoverBg: theme.colors.error,
        hoverColor: theme.colors.textInverse,
        hoverBorder: theme.colors.error,
      };
    case 'default':
      return {
        bg: theme.colors.bgPrimary,
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: theme.colors.borderPrimary,
      };
    case 'text':
      return {
        bg: 'transparent',
        color: theme.colors.textPrimary,
        border: 'transparent',
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: 'transparent',
      };
    case 'link':
      return {
        bg: 'transparent',
        color: theme.colors.primary,
        border: 'transparent',
        hoverBg: 'transparent',
        hoverColor: theme.colors.primaryHover,
        hoverBorder: 'transparent',
      };
    case 'ghost':
      return {
        bg: 'transparent',
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
        hoverBg: theme.colors.bgSecondary,
        hoverColor: theme.colors.textPrimary,
        hoverBorder: theme.colors.borderPrimary,
      };
    case 'primary':
    default:
      return {
        bg: theme.colors.buttonPrimary,
        color: theme.colors.buttonPrimaryText,
        border: theme.colors.buttonPrimary,
        hoverBg: theme.colors.buttonPrimaryHover,
        hoverColor: theme.colors.buttonPrimaryText,
        hoverBorder: theme.colors.buttonPrimaryHover,
      };
  }
};

/**
 * Resolves height for each button size
 */
export const resolveRediaccButtonHeight = (theme: StyledTheme, size: ButtonSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.dimensions.CONTROL_HEIGHT_SM; // 28px
    case 'md':
    default:
      return theme.dimensions.CONTROL_HEIGHT; // 32px
  }
};

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
    line-height: 1.2;
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
