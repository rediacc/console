import { Checkbox as AntCheckbox } from 'antd';
import styled from 'styled-components';

/**
 * Styled RediaccCheckbox component
 *
 * Theme-aware checkbox with consistent styling.
 */
export const StyledRediaccCheckbox = styled(AntCheckbox)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textPrimary};

    /* Checkbox indicator styles */
    .ant-checkbox {
      .ant-checkbox-inner {
        border-radius: ${({ theme }) => theme.borderRadius.SM}px;
        border-color: ${({ theme }) => theme.colors.borderPrimary};
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      }

      &:hover .ant-checkbox-inner {
        border-color: ${({ theme }) => theme.colors.primary};
      }
    }

    /* Checked state */
    .ant-checkbox-checked {
      .ant-checkbox-inner {
        background-color: ${({ theme }) => theme.colors.primary};
        border-color: ${({ theme }) => theme.colors.primary};
      }

      &::after {
        border-color: ${({ theme }) => theme.colors.primary};
      }
    }

    /* Indeterminate state */
    .ant-checkbox-indeterminate {
      .ant-checkbox-inner {
        &::after {
          background-color: ${({ theme }) => theme.colors.primary};
        }
      }
    }

    /* Disabled state */
    &.ant-checkbox-wrapper-disabled {
      cursor: not-allowed;
      opacity: 0.6;

      .ant-checkbox-disabled .ant-checkbox-inner {
        background-color: ${({ theme }) => theme.colors.bgSecondary};
        border-color: ${({ theme }) => theme.colors.borderSecondary};
      }
    }

    /* Focus state */
    .ant-checkbox-input:focus-visible + .ant-checkbox-inner {
      border-color: ${({ theme }) => theme.colors.primary};
      box-shadow: 0 0 0 2px ${({ theme }) => theme.colors.primaryBg};
    }
  }
`;
