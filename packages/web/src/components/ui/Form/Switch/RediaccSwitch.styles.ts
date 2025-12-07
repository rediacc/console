import { Switch as AntSwitch } from 'antd';
import styled from 'styled-components';

/**
 * Styled RediaccSwitch component
 *
 * Theme-aware toggle switch with consistent styling.
 */
export const StyledRediaccSwitch = styled(AntSwitch)`
  && {
    /* Unchecked state */
    background-color: ${({ theme }) => theme.colors.bgTertiary};
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    &:hover:not(.ant-switch-disabled) {
      background-color: ${({ theme }) => theme.colors.textTertiary};
    }

    /* Checked state */
    &.ant-switch-checked {
      background-color: ${({ theme }) => theme.colors.primary};

      &:hover:not(.ant-switch-disabled) {
        background-color: ${({ theme }) => theme.colors.primaryHover};
      }
    }

    /* Handle styles */
    .ant-switch-handle {
      &::before {
        background-color: ${({ theme }) => theme.colors.bgPrimary};
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
      }
    }

    /* Disabled state */
    &.ant-switch-disabled {
      cursor: not-allowed;
      opacity: 0.6;
    }

    /* Loading state */
    &.ant-switch-loading {
      opacity: 0.8;
    }

    /* Focus state */
    &:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px ${({ theme }) => theme.colors.primaryBg};
    }

    /* Inner text styles */
    .ant-switch-inner {
      font-size: ${({ theme }) => theme.fontSize.XS}px;
    }
  }
`;
