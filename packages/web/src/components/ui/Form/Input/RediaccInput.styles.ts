import { Input as AntInput, InputNumber as AntInputNumber } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { InputSize, InputVariant } from './RediaccInput.types';

const { TextArea: AntTextArea, Password: AntPassword, Search: AntSearch } = AntInput;

/**
 * Shared input focus styles
 */
export const inputFocusStyles = css`
  &:focus,
  &.ant-input-affix-wrapper-focused {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    outline: none;
  }

  &.ant-input-status-error,
  &.ant-input-affix-wrapper-status-error {
    border-color: ${({ theme }) => theme.colors.error};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.error};
  }
`;

/**
 * Shared input prefix/suffix styles
 */
export const inputPrefixStyles = css`
  .ant-input-prefix {
    margin-left: ${({ theme }) => theme.spacing.SM_LG}px;
    margin-right: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textTertiary};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    transition: color 0.2s ease;

    .anticon {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }

  .ant-input-suffix {
    margin-right: ${({ theme }) => theme.spacing.SM_LG}px;
  }

  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

/**
 * Resolves height for each input size
 */
export const resolveInputHeight = (theme: StyledTheme, size: InputSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.dimensions.INPUT_HEIGHT_SM; // 36px
    case 'md':
    default:
      return theme.dimensions.INPUT_HEIGHT; // 44px
  }
};

/**
 * Resolves variant-specific styles for inputs
 */
const resolveVariantStyles = (variant: InputVariant = 'default') => {
  switch (variant) {
    case 'default':
    default:
      return css``;
  }
};

/**
 * Base input styles shared across all input types
 */
const baseInputStyles = css<{
  $variant?: InputVariant;
  $size?: InputSize;
  $fullWidth?: boolean;
  $centered?: boolean;
}>`
  && {
    height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    /* Full width modifier */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Centered text modifier */
    ${({ $centered }) =>
      $centered &&
      css`
        text-align: center;
      `}

    /* Variant-specific styles */
    ${({ $variant }) => resolveVariantStyles($variant)}

    /* Input wrapper padding adjustment */
    &.ant-input-affix-wrapper {
      padding: 0;
    }

    /* Actual input element styles */
    input.ant-input {
      padding: 0 ${({ theme }) => theme.spacing.SM_LG}px;
      height: 100%;
    }

    /* Apply prefix/suffix and focus styles */
    ${inputPrefixStyles}
    ${inputFocusStyles}
  }
`;

/**
 * Styled RediaccInput component
 */
export const StyledRediaccInput = styled(AntInput)<{
  $variant?: InputVariant;
  $size?: InputSize;
  $fullWidth?: boolean;
  $centered?: boolean;
}>`
  ${baseInputStyles}
`;

/**
 * Styled RediaccPasswordInput component
 */
export const StyledRediaccPasswordInput = styled(AntPassword)<{
  $size?: InputSize;
  $fullWidth?: boolean;
  $centered?: boolean;
}>`
  && {
    height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;

    /* Full width modifier */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Centered text modifier */
    ${({ $centered }) =>
      $centered &&
      css`
        input.ant-input {
          text-align: center;
        }
      `}

    /* Input wrapper padding adjustment */
    &.ant-input-affix-wrapper {
      padding: 0;
    }

    /* Actual input element styles */
    input.ant-input {
      padding: 0 ${({ theme }) => theme.spacing.SM_LG}px;
      height: 100%;
    }

    /* Apply prefix styles */
    ${inputPrefixStyles}

    /* Password visibility icon styles */
    .ant-input-suffix {
      margin-left: ${({ theme }) => theme.spacing.SM}px;

      .ant-input-password-icon {
        color: ${({ theme }) => theme.colors.textTertiary};
        font-size: ${({ theme }) => theme.fontSize.LG}px;
        transition: ${({ theme }) => theme.transitions.FAST};
        cursor: pointer;
        padding: ${({ theme }) => theme.spacing.XS}px;
        border-radius: ${({ theme }) => theme.borderRadius.SM}px;

        &:hover {
          color: ${({ theme }) => theme.colors.textSecondary};
          background-color: ${({ theme }) => theme.colors.bgHover};
        }
      }
    }

    /* Apply focus styles */
    ${inputFocusStyles}
  }
`;

/**
 * Styled RediaccTextArea component
 */
export const StyledRediaccTextArea = styled(AntTextArea)<{
  $fullWidth?: boolean;
  $resize?: 'none' | 'vertical' | 'horizontal' | 'both';
}>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    resize: ${({ $resize }) => $resize || 'vertical'};

    /* Full width modifier */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Apply focus styles */
    ${inputFocusStyles}
  }
`;

/**
 * Styled RediaccInputNumber component
 */
export const StyledRediaccInputNumber = styled(AntInputNumber)<{
  $size?: InputSize;
  $fullWidth?: boolean;
}>`
  && {
    height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    /* Full width modifier */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Input wrapper padding adjustment */
    &.ant-input-number-affix-wrapper {
      padding: 0;
    }

    /* Actual input element styles */
    .ant-input-number-input {
      padding: 0 ${({ theme }) => theme.spacing.SM_LG}px;
      height: 100%;
    }

    /* Apply prefix/suffix styles */
    ${inputPrefixStyles}

    /* Apply focus styles */
    ${inputFocusStyles}
  }
`;

/**
 * Styled RediaccSearchInput component
 */
export const StyledRediaccSearchInput = styled(AntSearch)<{
  $size?: InputSize;
  $fullWidth?: boolean;
}>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    min-height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;

    /* Full width modifier */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Input wrapper */
    .ant-input-wrapper {
      height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;
    }

    /* Search input specific styles */
    input.ant-input {
      height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;
      border-radius: ${({ theme }) => theme.borderRadius.LG}px 0 0 ${({ theme }) =>
        theme.borderRadius.LG}px;
    }

    /* Search button */
    .ant-input-search-button {
      height: ${({ theme, $size }) => resolveInputHeight(theme, $size)}px;
    }

    /* Apply focus styles */
    ${inputFocusStyles}
  }
`;
