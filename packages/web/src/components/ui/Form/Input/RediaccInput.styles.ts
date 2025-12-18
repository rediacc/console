import { Input as AntInput, InputNumber as AntInputNumber } from 'antd';
import styled, { css } from 'styled-components';
import type { InputVariant } from './RediaccInput.types';

const { TextArea: AntTextArea, Password: AntPassword, Search: AntSearch } = AntInput;

/**
 * Shared input focus styles
 */
export const inputFocusStyles = css`
  &:focus,
  &.ant-input-affix-wrapper-focused {
    outline: none;
  }

  &.ant-input-status-error,
  &.ant-input-affix-wrapper-status-error {
  }
`;

/**
 * Shared input prefix/suffix styles
 */
export const inputPrefixStyles = css`
  .ant-input-prefix {
    font-size: ${({ theme }) => theme.fontSize.LG}px;

    .anticon {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }

  .ant-input-suffix {
  }

  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
  }
`;

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
  $fullWidth?: boolean;
  $centered?: boolean;
}>`
  && {
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;

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
  $fullWidth?: boolean;
  $centered?: boolean;
}>`
  ${baseInputStyles}
`;

/**
 * Styled RediaccPasswordInput component
 */
export const StyledRediaccPasswordInput = styled(AntPassword)<{
  $fullWidth?: boolean;
  $centered?: boolean;
}>`
  && {
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
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

      .ant-input-password-icon {
        font-size: ${({ theme }) => theme.fontSize.LG}px;
        cursor: pointer;
        padding: ${({ theme }) => theme.spacing.XS}px;

        &:hover {
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
    font-size: ${({ theme }) => theme.fontSize.SM}px;
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
  $fullWidth?: boolean;
}>`
  && {
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;

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
  $fullWidth?: boolean;
}>`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;

    /* Full width modifier */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    /* Input wrapper */
    .ant-input-wrapper {
      height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    }

    /* Search input specific styles */
    input.ant-input {
      height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    }

    /* Search button */
    .ant-input-search-button {
      height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    }

    /* Apply focus styles */
    ${inputFocusStyles}
  }
`;
