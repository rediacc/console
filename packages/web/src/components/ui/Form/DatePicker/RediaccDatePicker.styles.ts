import { DatePicker as AntDatePicker } from 'antd';
import styled, { css } from 'styled-components';
import { disabledState } from '@/styles/mixins';

const { RangePicker: AntRangePicker } = AntDatePicker;

/**
 * Shared date picker styles
 */
const baseDatePickerStyles = css<{ $minWidth?: number }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;

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

        &::placeholder {
        }
      }
    }

    /* Icons */
    .ant-picker-suffix,
    .ant-picker-clear {
    }

    .ant-picker-clear:hover {
    }

    /* Focus state */
    &.ant-picker-focused {
    }

    /* Error state */
    &.ant-picker-status-error {
      &.ant-picker-focused {
      }
    }

    /* Warning state */
    &.ant-picker-status-warning {
      &.ant-picker-focused {
      }
    }

    /* Disabled state */
    &.ant-picker-disabled {
      ${disabledState}
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
    }

    /* Active bar */
    .ant-picker-active-bar {
    }
  }
`;
