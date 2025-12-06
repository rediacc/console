import styled, { css } from 'styled-components';
import { DatePicker as AntDatePicker } from 'antd';

const { RangePicker: AntRangePicker } = AntDatePicker;

/**
 * Shared date picker styles
 */
const baseDatePickerStyles = css<{ $minWidth?: number }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    /* Min width modifier */
    ${({ $minWidth }) =>
      $minWidth &&
      css`
        min-width: ${$minWidth}px;
      `}

    /* Input container styles */
    .ant-picker-input {
      > input {
        font-size: ${({ theme }) => theme.fontSize.SM}px;
        color: ${({ theme }) => theme.colors.textPrimary};

        &::placeholder {
          color: ${({ theme }) => theme.colors.textTertiary};
        }
      }
    }

    /* Icons */
    .ant-picker-suffix,
    .ant-picker-clear {
      color: ${({ theme }) => theme.colors.textTertiary};
      transition: color 0.2s ease;
    }

    .ant-picker-clear:hover {
      color: ${({ theme }) => theme.colors.textSecondary};
    }

    /* Hover state */
    &:hover:not(.ant-picker-disabled) {
      border-color: ${({ theme }) => theme.colors.primary};
    }

    /* Focus state */
    &.ant-picker-focused {
      border-color: ${({ theme }) => theme.colors.primary};
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    }

    /* Error state */
    &.ant-picker-status-error {
      border-color: ${({ theme }) => theme.colors.error};

      &.ant-picker-focused {
        box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.error};
      }
    }

    /* Warning state */
    &.ant-picker-status-warning {
      border-color: ${({ theme }) => theme.colors.warning};

      &.ant-picker-focused {
        box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.warning};
      }
    }

    /* Disabled state */
    &.ant-picker-disabled {
      cursor: not-allowed;
      opacity: 0.6;
      background-color: ${({ theme }) => theme.colors.bgSecondary};
    }
  }
`;

/**
 * Styled RediaccDatePicker component
 *
 * Theme-aware date picker with consistent styling.
 */
export const StyledRediaccDatePicker = styled(AntDatePicker)<{ $minWidth?: number }>`
  ${baseDatePickerStyles}
`;

/**
 * Styled RediaccRangePicker component
 *
 * Theme-aware date range picker with consistent styling.
 */
export const StyledRediaccRangePicker = styled(AntRangePicker)<{ $minWidth?: number }>`
  ${baseDatePickerStyles}

  && {
    /* Range separator */
    .ant-picker-range-separator {
      color: ${({ theme }) => theme.colors.textTertiary};
    }

    /* Active bar */
    .ant-picker-active-bar {
      background-color: ${({ theme }) => theme.colors.primary};
    }
  }
`;
