import styled from 'styled-components';
import { Radio as AntRadio } from 'antd';

const { Group: AntRadioGroup, Button: AntRadioButton } = AntRadio;

/**
 * Styled Rediacc Radio Group component
 *
 * Theme-aware radio button group with consistent styling.
 */
export const StyledRediaccRadioGroup = styled(AntRadioGroup)`
  && {
    display: inline-flex;

    /* Radio button styles within group */
    .ant-radio-button-wrapper {
      font-size: ${({ theme }) => theme.fontSize.SM}px;
      color: ${({ theme }) => theme.colors.textSecondary};
      background-color: ${({ theme }) => theme.colors.bgPrimary};
      border-color: ${({ theme }) => theme.colors.borderPrimary};
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        color: ${({ theme }) => theme.colors.primary};
        border-color: ${({ theme }) => theme.colors.primary};
      }

      &:first-child {
        border-radius: ${({ theme }) => theme.borderRadius.MD}px 0 0
          ${({ theme }) => theme.borderRadius.MD}px;
      }

      &:last-child {
        border-radius: 0 ${({ theme }) => theme.borderRadius.MD}px
          ${({ theme }) => theme.borderRadius.MD}px 0;
      }
    }

    /* Checked state */
    .ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled) {
      color: ${({ theme }) => theme.colors.primary};
      background-color: ${({ theme }) => theme.colors.primaryBg};
      border-color: ${({ theme }) => theme.colors.primary};

      &::before {
        background-color: ${({ theme }) => theme.colors.primary};
      }

      &:hover {
        color: ${({ theme }) => theme.colors.primaryHover};
        border-color: ${({ theme }) => theme.colors.primaryHover};
      }
    }

    /* Disabled state */
    .ant-radio-button-wrapper-disabled {
      cursor: not-allowed;
      opacity: 0.6;
      background-color: ${({ theme }) => theme.colors.bgSecondary};
      border-color: ${({ theme }) => theme.colors.borderSecondary};
      color: ${({ theme }) => theme.colors.textTertiary};
    }

    /* Focus state */
    .ant-radio-button-wrapper:focus-within {
      box-shadow: 0 0 0 2px ${({ theme }) => theme.colors.primaryBg};
    }
  }
`;

/**
 * Styled Rediacc Radio Button component
 *
 * Individual radio button for use within RediaccRadio.Group.
 */
export const StyledRediaccRadioButton = styled(AntRadioButton)`
  && {
    /* Base styles are handled by the group */
  }
`;
